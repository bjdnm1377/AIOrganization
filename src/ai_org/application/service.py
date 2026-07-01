from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from functools import wraps
from typing import Any, Concatenate, cast
from uuid import uuid4

from ai_org.domain.enums import (
    ActorType,
    AgentResultStatus,
    ApprovalStatus,
    ProjectStatus,
    ReviewDecision,
    RiskLevel,
    TaskStatus,
    WorkerRunStatus,
    WorkerType,
)
from ai_org.domain.errors import ConflictError, NotFoundError, ValidationFailure
from ai_org.domain.models import Approval, AuditEvent, Project, Task, WorkerRun, utc_now
from ai_org.domain.state_machine import (
    ensure_approval_transition,
    ensure_project_transition,
    ensure_task_transition,
    ensure_worker_run_transition,
)
from ai_org.ports.repositories import Repository
from ai_org.ports.workers import WorkerRegistry, WorkerRequest
from ai_org.protocols.schemas import (
    AgentResult,
    ApprovalDecision,
    CreateProjectRequest,
    ProjectResponse,
    ReviewReport,
    TaskSpec,
    WorkflowStatus,
)
from ai_org.security import redact


def transactional[**P, R](
    method: Callable[Concatenate[Any, P], R],
) -> Callable[Concatenate[Any, P], R]:
    @wraps(method)
    def wrapped(self: Any, *args: P.args, **kwargs: P.kwargs) -> R:
        try:
            result = method(self, *args, **kwargs)
        except Exception:
            self._rollback_transaction()
            raise
        self._commit_transaction()
        return result

    return cast(Callable[Concatenate[Any, P], R], wrapped)


class ProjectApplicationService:
    def __init__(
        self,
        repo: Repository,
        worker_registry: WorkerRegistry,
        commit: Callable[[], None] | None = None,
        rollback: Callable[[], None] | None = None,
    ) -> None:
        self.repo = repo
        self.worker_registry = worker_registry
        self._commit_hook = commit or _noop
        self._rollback_hook = rollback or _noop

    @transactional
    def create_project(self, request: CreateProjectRequest) -> ProjectResponse:
        if request.idempotency_key:
            existing = self.repo.get_project_by_idempotency_key(request.idempotency_key)
            if existing:
                return self.get_project(existing.project_id)

        project = Project(
            project_id=f"proj_{uuid4().hex}",
            title=request.title,
            goal=request.goal,
            status=ProjectStatus.CREATED,
            success_criteria=request.success_criteria,
            idempotency_key=request.idempotency_key,
        )
        self.repo.add_project(project)
        task_specs = request.tasks or [
            TaskSpec(
                title="Default mock research task",
                objective=f"Produce deterministic mock evidence for: {request.goal}",
                worker_type=WorkerType.RESEARCH,
                risk_level=RiskLevel.LOW,
            )
        ]
        for index, spec in enumerate(task_specs):
            status = TaskStatus.READY if not spec.dependencies else TaskStatus.PENDING
            task = Task(
                task_id=f"task_{uuid4().hex}",
                project_id=project.project_id,
                title=spec.title,
                objective=spec.objective,
                worker_type=spec.worker_type.value,
                status=status,
                risk_level=spec.risk_level,
                dependencies=spec.dependencies,
                acceptance_criteria=spec.acceptance_criteria,
                metadata=spec.metadata,
                max_attempts=spec.max_attempts,
                idempotency_key=f"{project.project_id}:task:{index}",
            )
            self.repo.add_task(task)
        self.audit(
            project.project_id,
            None,
            "project.created",
            ActorType.SYSTEM,
            "application",
            {"title": request.title, "task_count": len(task_specs)},
        )
        return self.get_project(project.project_id)

    def get_project(self, project_id: str) -> ProjectResponse:
        project = self._require_project(project_id)
        from ai_org.application.mappers import project_to_response

        return project_to_response(project)

    def get_status(self, project_id: str) -> WorkflowStatus:
        from ai_org.application.mappers import (
            approval_to_response,
            project_to_response,
            task_to_response,
            worker_run_to_response,
        )

        project = self._require_project(project_id)
        tasks = self.repo.list_tasks(project_id)
        approvals = self.repo.list_approvals(project_id)
        worker_runs = [run for task in tasks for run in self.repo.list_worker_runs(task.task_id)]
        return WorkflowStatus(
            project=project_to_response(project),
            tasks=[task_to_response(task) for task in tasks],
            approvals=[approval_to_response(approval) for approval in approvals],
            worker_runs=[worker_run_to_response(run) for run in worker_runs],
            waiting_for_approval=project.status == ProjectStatus.WAITING_APPROVAL,
        )

    @transactional
    def mark_project_running(self, project_id: str) -> None:
        project = self._require_project(project_id)
        if project.status in {ProjectStatus.COMPLETED, ProjectStatus.BLOCKED, ProjectStatus.FAILED}:
            return
        self._update_project_status(project, ProjectStatus.RUNNING)
        self.audit(project_id, None, "workflow.running", ActorType.SYSTEM, "workflow", {})

    @transactional
    def select_ready_task(self, project_id: str) -> Task | None:
        tasks = self.repo.list_tasks(project_id)
        accepted_ids = {task.task_id for task in tasks if task.status == TaskStatus.ACCEPTED}
        for task in tasks:
            if task.status == TaskStatus.PENDING and set(task.dependencies).issubset(accepted_ids):
                self._update_task_status(task, TaskStatus.READY)
                task = self._require_task(task.task_id)
            if task.status in {TaskStatus.READY, TaskStatus.REWORK_REQUIRED}:
                if task.attempt_count >= task.max_attempts:
                    self._update_task_status(task, TaskStatus.BLOCKED)
                    self.audit(
                        task.project_id,
                        task.task_id,
                        "task.max_attempts_reached",
                        ActorType.SYSTEM,
                        "workflow",
                        {"attempt_count": task.attempt_count, "max_attempts": task.max_attempts},
                    )
                    continue
                return task
        return None

    def task_requires_approval(self, task_id: str) -> bool:
        task = self._require_task(task_id)
        if task.risk_level not in {RiskLevel.HIGH, RiskLevel.CRITICAL}:
            return False
        approval = self.get_latest_task_approval(task.task_id)
        return approval is None or approval.status != ApprovalStatus.APPROVED

    @transactional
    def request_approval(self, task_id: str) -> Approval:
        task = self._require_task(task_id)
        project = self._require_project(task.project_id)
        key = f"approval:{task.task_id}:{task.attempt_count + 1}:execute"
        existing = self.repo.get_approval_by_idempotency_key(key)
        if existing:
            return existing
        approval = Approval(
            approval_id=f"appr_{uuid4().hex}",
            project_id=task.project_id,
            task_id=task.task_id,
            action="execute_high_risk_task",
            risk_level=task.risk_level,
            status=ApprovalStatus.PENDING,
            request_payload=redact(
                {
                    "task_title": task.title,
                    "objective": task.objective,
                    "risk_level": task.risk_level.value,
                }
            ),
            idempotency_key=key,
        )
        approval = self.repo.add_approval(approval)
        self._update_task_status(task, TaskStatus.WAITING_APPROVAL)
        self._update_project_status(project, ProjectStatus.WAITING_APPROVAL)
        self.audit(
            task.project_id,
            task.task_id,
            "approval.requested",
            ActorType.SYSTEM,
            "workflow",
            {"approval_id": approval.approval_id, "risk_level": task.risk_level.value},
        )
        return approval

    @transactional
    def apply_approval_decision(self, approval_id: str, decision: ApprovalDecision) -> Approval:
        approval = self._require_approval(approval_id)
        if approval.status != ApprovalStatus.PENDING:
            return approval
        target = (
            ApprovalStatus.APPROVED if decision.decision == "APPROVED" else ApprovalStatus.REJECTED
        )
        ensure_approval_transition(approval.status, target)
        updated = replace(
            approval,
            status=target,
            decision=decision.decision,
            decision_reason=decision.decision_reason,
            decided_at=datetime.now(tz=UTC),
        )
        self.repo.update_approval(updated, expected_version=approval.version)
        task = self._require_task(approval.task_id)
        project = self._require_project(approval.project_id)
        if target == ApprovalStatus.APPROVED:
            self._update_task_status(task, TaskStatus.READY)
            self._update_project_status(project, ProjectStatus.RUNNING)
            event_type = "approval.approved"
        else:
            self._update_task_status(task, TaskStatus.BLOCKED)
            self._update_project_status(project, ProjectStatus.BLOCKED)
            event_type = "approval.rejected"
        self.audit(
            approval.project_id,
            approval.task_id,
            event_type,
            ActorType.USER,
            "approval-api",
            {"approval_id": approval.approval_id, "reason": decision.decision_reason},
        )
        return self._require_approval(approval_id)

    @transactional
    def dispatch_worker(self, task_id: str) -> AgentResult:
        task = self._require_task(task_id)
        if task.status == TaskStatus.ACCEPTED:
            raise ConflictError("Accepted tasks cannot be executed again")
        attempt_number = task.attempt_count + 1
        run_key = f"worker:{task.task_id}:{attempt_number}:produce"
        existing = self.repo.get_worker_run_by_idempotency_key(run_key)
        if existing:
            if existing.structured_output:
                return AgentResult.model_validate(existing.structured_output)
            raise ConflictError(f"WorkerRun {existing.run_id} is already in progress")
        new_worker_run = WorkerRun(
            run_id=f"run_{uuid4().hex}",
            task_id=task.task_id,
            worker_type=task.worker_type,
            status=WorkerRunStatus.RUNNING,
            structured_input=redact(
                {
                    "objective": task.objective,
                    "attempt_number": attempt_number,
                    "task_metadata": task.metadata,
                }
            ),
            structured_output=None,
            attempt_number=attempt_number,
            idempotency_key=run_key,
            started_at=utc_now(),
        )
        worker_run = self.repo.add_worker_run(new_worker_run)
        if worker_run.structured_output:
            return AgentResult.model_validate(worker_run.structured_output)
        if worker_run.run_id != new_worker_run.run_id:
            raise ConflictError(f"WorkerRun {worker_run.run_id} is already in progress")

        updated_task = replace(task, attempt_count=attempt_number)
        self.repo.update_task(updated_task, expected_version=task.version)
        self._update_task_status(self._require_task(task.task_id), TaskStatus.RUNNING)
        self.audit(
            task.project_id,
            task.task_id,
            "worker.dispatched",
            ActorType.SYSTEM,
            "worker-dispatcher",
            {"run_id": worker_run.run_id, "worker_type": task.worker_type},
        )
        self._commit_transaction()
        worker = self.worker_registry.get_worker(task.worker_type)
        result = worker.run(
            WorkerRequest(
                task=self._require_task(task.task_id),
                attempt_number=attempt_number,
                structured_input=worker_run.structured_input,
            )
        )
        self.complete_worker_run(worker_run.run_id, result)
        return result

    @transactional
    def complete_worker_run(self, run_id: str, result: AgentResult) -> None:
        run = self._require_worker_run(run_id)
        target = (
            WorkerRunStatus.SUCCEEDED
            if result.status
            in {
                AgentResultStatus.SUCCEEDED,
                AgentResultStatus.DRY_RUN,
                AgentResultStatus.NOT_CONFIGURED,
            }
            else WorkerRunStatus.FAILED
        )
        ensure_worker_run_transition(run.status, target)
        updated = replace(
            run,
            status=target,
            structured_output=redact(result.model_dump(mode="json")),
            finished_at=utc_now(),
            error=None if target == WorkerRunStatus.SUCCEEDED else result.summary,
        )
        self.repo.update_worker_run(updated, expected_version=run.version)
        task = self._require_task(run.task_id)
        if target == WorkerRunStatus.SUCCEEDED:
            self._update_task_status(task, TaskStatus.REVIEWING)
            self._update_project_status(
                self._require_project(task.project_id), ProjectStatus.REVIEWING
            )
        else:
            self._update_task_status(task, TaskStatus.FAILED)
        self.audit(
            task.project_id,
            task.task_id,
            "worker.completed",
            ActorType.WORKER,
            run.worker_type,
            {"run_id": run.run_id, "status": target.value},
        )
        if result.metadata.get("coding_worker") is True:
            self.audit(
                task.project_id,
                task.task_id,
                "coding_worker.completed",
                ActorType.WORKER,
                run.worker_type,
                {
                    "run_id": run.run_id,
                    "mode": result.metadata.get("codex_mode"),
                    "changed_files": result.metadata.get("changed_files", []),
                    "violations": result.metadata.get("policy_violations", []),
                },
            )

    def deterministic_validation(self, result: AgentResult) -> None:
        if result.status == AgentResultStatus.FAILED:
            raise ValidationFailure(result.summary)

    @transactional
    def review_result(self, task_id: str, result: AgentResult) -> ReviewReport:
        task = self._require_task(task_id)
        if task.worker_type == WorkerType.REVIEW.value:
            raise ConflictError("Production worker cannot be the review worker")
        review_attempt = task.attempt_count
        run_key = f"worker:{task.task_id}:{review_attempt}:review"
        existing = self.repo.get_worker_run_by_idempotency_key(run_key)
        if existing:
            if existing.structured_output:
                return ReviewReport.model_validate(existing.structured_output)
            raise ConflictError(f"Review WorkerRun {existing.run_id} is already in progress")
        new_review_run = WorkerRun(
            run_id=f"run_{uuid4().hex}",
            task_id=task.task_id,
            worker_type=WorkerType.REVIEW.value,
            status=WorkerRunStatus.RUNNING,
            structured_input=redact({"reviewing_run_for_task": task.task_id}),
            structured_output=None,
            attempt_number=review_attempt,
            idempotency_key=run_key,
            started_at=utc_now(),
        )
        run = self.repo.add_worker_run(new_review_run)
        if run.structured_output:
            return ReviewReport.model_validate(run.structured_output)
        if run.run_id != new_review_run.run_id:
            raise ConflictError(f"Review WorkerRun {run.run_id} is already in progress")
        report = self.worker_registry.get_review_worker().review(task, result, review_attempt)
        updated = replace(
            run,
            status=WorkerRunStatus.SUCCEEDED,
            structured_output=redact(report.model_dump(mode="json")),
            finished_at=utc_now(),
        )
        self.repo.update_worker_run(updated, expected_version=run.version)
        self.audit(
            task.project_id,
            task.task_id,
            "review.completed",
            ActorType.REVIEWER,
            WorkerType.REVIEW.value,
            {"run_id": run.run_id, "decision": report.decision.value},
        )
        return report

    @transactional
    def handle_review_decision(self, task_id: str, report: ReviewReport) -> str:
        task = self._require_task(task_id)
        if report.decision == ReviewDecision.ACCEPTED:
            self._update_task_status(task, TaskStatus.ACCEPTED)
            self.audit(
                task.project_id,
                task.task_id,
                "task.accepted",
                ActorType.SYSTEM,
                "workflow",
                {"confidence": report.confidence},
            )
            return "accepted"
        if (
            report.decision == ReviewDecision.REWORK_REQUIRED
            and task.attempt_count < task.max_attempts
        ):
            self._update_task_status(task, TaskStatus.REWORK_REQUIRED)
            self._update_project_status(
                self._require_project(task.project_id), ProjectStatus.RUNNING
            )
            self.audit(
                task.project_id,
                task.task_id,
                "task.rework_required",
                ActorType.REVIEWER,
                WorkerType.REVIEW.value,
                {"attempt_count": task.attempt_count, "max_attempts": task.max_attempts},
            )
            return "rework"
        self._update_task_status(task, TaskStatus.BLOCKED)
        self._update_project_status(self._require_project(task.project_id), ProjectStatus.BLOCKED)
        self.audit(
            task.project_id,
            task.task_id,
            "task.blocked",
            ActorType.SYSTEM,
            "workflow",
            {"decision": report.decision.value, "attempt_count": task.attempt_count},
        )
        return "blocked"

    @transactional
    def finalize_project(self, project_id: str) -> None:
        project = self._require_project(project_id)
        tasks = self.repo.list_tasks(project_id)
        if all(task.status == TaskStatus.ACCEPTED for task in tasks):
            self._update_project_status(project, ProjectStatus.COMPLETED)
            self.audit(project_id, None, "project.completed", ActorType.SYSTEM, "workflow", {})
            return
        if any(task.status == TaskStatus.BLOCKED for task in tasks):
            self._update_project_status(project, ProjectStatus.BLOCKED)
            self.audit(project_id, None, "project.blocked", ActorType.SYSTEM, "workflow", {})

    def get_latest_task_approval(self, task_id: str) -> Approval | None:
        task = self._require_task(task_id)
        approvals = [
            approval
            for approval in self.repo.list_approvals(task.project_id)
            if approval.task_id == task_id
        ]
        return approvals[-1] if approvals else None

    def audit(
        self,
        project_id: str | None,
        task_id: str | None,
        event_type: str,
        actor_type: ActorType,
        actor_id: str,
        payload: dict[str, object],
    ) -> None:
        self.repo.add_audit_event(
            AuditEvent(
                event_id=f"evt_{uuid4().hex}",
                project_id=project_id,
                task_id=task_id,
                event_type=event_type,
                actor_type=actor_type,
                actor_id=actor_id,
                payload=redact(payload),
            )
        )

    def _update_project_status(self, project: Project, status: ProjectStatus) -> None:
        if project.status == status:
            return
        ensure_project_transition(project.status, status)
        self.repo.update_project(
            replace(project, status=status, updated_at=utc_now()),
            expected_version=project.version,
        )

    def _update_task_status(self, task: Task, status: TaskStatus) -> None:
        if task.status == status:
            return
        ensure_task_transition(task.status, status)
        self.repo.update_task(
            replace(task, status=status, updated_at=utc_now()),
            expected_version=task.version,
        )

    def _require_project(self, project_id: str) -> Project:
        project = self.repo.get_project(project_id)
        if project is None:
            raise NotFoundError(f"Project {project_id} not found")
        return project

    def _require_task(self, task_id: str) -> Task:
        task = self.repo.get_task(task_id)
        if task is None:
            raise NotFoundError(f"Task {task_id} not found")
        return task

    def _require_approval(self, approval_id: str) -> Approval:
        approval = self.repo.get_approval(approval_id)
        if approval is None:
            raise NotFoundError(f"Approval {approval_id} not found")
        return approval

    def _require_worker_run(self, run_id: str) -> WorkerRun:
        run = self.repo.get_worker_run(run_id)
        if run is None:
            raise NotFoundError(f"WorkerRun {run_id} not found")
        return run

    def _commit_transaction(self) -> None:
        self._commit_hook()

    def _rollback_transaction(self) -> None:
        self._rollback_hook()


def _noop() -> None:
    return None
