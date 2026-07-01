from __future__ import annotations

from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ai_org.adapters.postgres.models import (
    ApprovalRow,
    AuditEventRow,
    ProjectRow,
    TaskRow,
    WorkerRunRow,
)
from ai_org.domain.enums import (
    ActorType,
    ApprovalStatus,
    ProjectStatus,
    RiskLevel,
    TaskStatus,
    WorkerRunStatus,
)
from ai_org.domain.errors import ConflictError
from ai_org.domain.models import Approval, AuditEvent, Project, Task, WorkerRun
from ai_org.ports.repositories import Repository


class SqlAlchemyRepository(Repository):
    def __init__(self, session: Session) -> None:
        self.session = session

    def add_project(self, project: Project) -> None:
        self.session.add(_project_row(project))
        self._flush()

    def get_project(self, project_id: str) -> Project | None:
        row = self.session.get(ProjectRow, project_id)
        return _project(row) if row else None

    def get_project_by_idempotency_key(self, key: str) -> Project | None:
        row = self.session.scalar(select(ProjectRow).where(ProjectRow.idempotency_key == key))
        return _project(row) if row else None

    def update_project(self, project: Project, expected_version: int) -> None:
        stmt = (
            update(ProjectRow)
            .where(
                ProjectRow.project_id == project.project_id, ProjectRow.version == expected_version
            )
            .values(
                title=project.title,
                goal=project.goal,
                status=project.status.value,
                success_criteria=project.success_criteria,
                updated_at=project.updated_at,
                version=expected_version + 1,
            )
        )
        self._expect_one(stmt)

    def add_task(self, task: Task) -> None:
        self.session.add(_task_row(task))
        self._flush()

    def get_task(self, task_id: str) -> Task | None:
        row = self.session.get(TaskRow, task_id)
        return _task(row) if row else None

    def list_tasks(self, project_id: str) -> list[Task]:
        rows = self.session.scalars(select(TaskRow).where(TaskRow.project_id == project_id)).all()
        return [_task(row) for row in rows]

    def update_task(self, task: Task, expected_version: int) -> None:
        stmt = (
            update(TaskRow)
            .where(TaskRow.task_id == task.task_id, TaskRow.version == expected_version)
            .values(
                title=task.title,
                objective=task.objective,
                worker_type=task.worker_type,
                status=task.status.value,
                risk_level=task.risk_level.value,
                dependencies=task.dependencies,
                acceptance_criteria=task.acceptance_criteria,
                attempt_count=task.attempt_count,
                max_attempts=task.max_attempts,
                updated_at=task.updated_at,
                version=expected_version + 1,
            )
        )
        self._expect_one(stmt)

    def add_worker_run(self, worker_run: WorkerRun) -> WorkerRun:
        existing = self.get_worker_run_by_idempotency_key(worker_run.idempotency_key)
        if existing:
            return existing
        self.session.add(_worker_run_row(worker_run))
        self._flush()
        return worker_run

    def get_worker_run(self, run_id: str) -> WorkerRun | None:
        row = self.session.get(WorkerRunRow, run_id)
        return _worker_run(row) if row else None

    def get_worker_run_by_idempotency_key(self, key: str) -> WorkerRun | None:
        row = self.session.scalar(select(WorkerRunRow).where(WorkerRunRow.idempotency_key == key))
        return _worker_run(row) if row else None

    def list_worker_runs(self, task_id: str | None = None) -> list[WorkerRun]:
        stmt = select(WorkerRunRow)
        if task_id is not None:
            stmt = stmt.where(WorkerRunRow.task_id == task_id)
        return [_worker_run(row) for row in self.session.scalars(stmt).all()]

    def update_worker_run(self, worker_run: WorkerRun, expected_version: int) -> None:
        stmt = (
            update(WorkerRunRow)
            .where(
                WorkerRunRow.run_id == worker_run.run_id, WorkerRunRow.version == expected_version
            )
            .values(
                status=worker_run.status.value,
                structured_input=worker_run.structured_input,
                structured_output=worker_run.structured_output,
                finished_at=worker_run.finished_at,
                error=worker_run.error,
                version=expected_version + 1,
            )
        )
        self._expect_one(stmt)

    def add_approval(self, approval: Approval) -> Approval:
        if approval.idempotency_key:
            existing = self.get_approval_by_idempotency_key(approval.idempotency_key)
            if existing:
                return existing
        self.session.add(_approval_row(approval))
        self._flush()
        return approval

    def get_approval(self, approval_id: str) -> Approval | None:
        row = self.session.get(ApprovalRow, approval_id)
        return _approval(row) if row else None

    def get_approval_by_idempotency_key(self, key: str) -> Approval | None:
        row = self.session.scalar(select(ApprovalRow).where(ApprovalRow.idempotency_key == key))
        return _approval(row) if row else None

    def list_approvals(self, project_id: str) -> list[Approval]:
        rows = self.session.scalars(
            select(ApprovalRow).where(ApprovalRow.project_id == project_id)
        ).all()
        return [_approval(row) for row in rows]

    def update_approval(self, approval: Approval, expected_version: int) -> None:
        stmt = (
            update(ApprovalRow)
            .where(
                ApprovalRow.approval_id == approval.approval_id,
                ApprovalRow.version == expected_version,
            )
            .values(
                status=approval.status.value,
                decision=approval.decision,
                decision_reason=approval.decision_reason,
                decided_at=approval.decided_at,
                version=expected_version + 1,
            )
        )
        self._expect_one(stmt)

    def add_audit_event(self, event: AuditEvent) -> None:
        self.session.add(_audit_event_row(event))
        self._flush()

    def list_audit_events(self, project_id: str) -> list[AuditEvent]:
        rows = self.session.scalars(
            select(AuditEventRow)
            .where(AuditEventRow.project_id == project_id)
            .order_by(AuditEventRow.created_at)
        ).all()
        return [_audit_event(row) for row in rows]

    def _flush(self) -> None:
        try:
            self.session.flush()
        except IntegrityError as exc:
            raise ConflictError("Database integrity conflict") from exc

    def _expect_one(self, stmt: Any) -> None:
        result: Any = self.session.execute(stmt)
        if result.rowcount != 1:
            raise ConflictError("Optimistic lock conflict")


def _project_row(project: Project) -> ProjectRow:
    return ProjectRow(
        project_id=project.project_id,
        title=project.title,
        goal=project.goal,
        status=project.status.value,
        success_criteria=project.success_criteria,
        created_at=project.created_at,
        updated_at=project.updated_at,
        version=project.version,
        idempotency_key=project.idempotency_key,
    )


def _project(row: ProjectRow) -> Project:
    return Project(
        project_id=row.project_id,
        title=row.title,
        goal=row.goal,
        status=ProjectStatus(row.status),
        success_criteria=list(row.success_criteria),
        created_at=row.created_at,
        updated_at=row.updated_at,
        version=row.version,
        idempotency_key=row.idempotency_key,
    )


def _task_row(task: Task) -> TaskRow:
    return TaskRow(
        task_id=task.task_id,
        project_id=task.project_id,
        title=task.title,
        objective=task.objective,
        worker_type=task.worker_type,
        status=task.status.value,
        risk_level=task.risk_level.value,
        dependencies=task.dependencies,
        acceptance_criteria=task.acceptance_criteria,
        attempt_count=task.attempt_count,
        max_attempts=task.max_attempts,
        created_at=task.created_at,
        updated_at=task.updated_at,
        version=task.version,
        idempotency_key=task.idempotency_key,
    )


def _task(row: TaskRow) -> Task:
    return Task(
        task_id=row.task_id,
        project_id=row.project_id,
        title=row.title,
        objective=row.objective,
        worker_type=row.worker_type,
        status=TaskStatus(row.status),
        risk_level=RiskLevel(row.risk_level),
        dependencies=list(row.dependencies),
        acceptance_criteria=list(row.acceptance_criteria),
        attempt_count=row.attempt_count,
        max_attempts=row.max_attempts,
        created_at=row.created_at,
        updated_at=row.updated_at,
        version=row.version,
        idempotency_key=row.idempotency_key,
    )


def _worker_run_row(run: WorkerRun) -> WorkerRunRow:
    return WorkerRunRow(
        run_id=run.run_id,
        task_id=run.task_id,
        worker_type=run.worker_type,
        status=run.status.value,
        structured_input=run.structured_input,
        structured_output=run.structured_output,
        attempt_number=run.attempt_number,
        idempotency_key=run.idempotency_key,
        started_at=run.started_at,
        finished_at=run.finished_at,
        error=run.error,
        version=run.version,
    )


def _worker_run(row: WorkerRunRow) -> WorkerRun:
    return WorkerRun(
        run_id=row.run_id,
        task_id=row.task_id,
        worker_type=row.worker_type,
        status=WorkerRunStatus(row.status),
        structured_input=dict(row.structured_input),
        structured_output=dict(row.structured_output) if row.structured_output else None,
        attempt_number=row.attempt_number,
        idempotency_key=row.idempotency_key,
        started_at=row.started_at,
        finished_at=row.finished_at,
        error=row.error,
        version=row.version,
    )


def _approval_row(approval: Approval) -> ApprovalRow:
    return ApprovalRow(
        approval_id=approval.approval_id,
        project_id=approval.project_id,
        task_id=approval.task_id,
        action=approval.action,
        risk_level=approval.risk_level.value,
        status=approval.status.value,
        request_payload=approval.request_payload,
        decision=approval.decision,
        decision_reason=approval.decision_reason,
        created_at=approval.created_at,
        decided_at=approval.decided_at,
        version=approval.version,
        idempotency_key=approval.idempotency_key,
    )


def _approval(row: ApprovalRow) -> Approval:
    return Approval(
        approval_id=row.approval_id,
        project_id=row.project_id,
        task_id=row.task_id,
        action=row.action,
        risk_level=RiskLevel(row.risk_level),
        status=ApprovalStatus(row.status),
        request_payload=dict(row.request_payload),
        decision=row.decision,
        decision_reason=row.decision_reason,
        created_at=row.created_at,
        decided_at=row.decided_at,
        version=row.version,
        idempotency_key=row.idempotency_key,
    )


def _audit_event_row(event: AuditEvent) -> AuditEventRow:
    return AuditEventRow(
        event_id=event.event_id,
        project_id=event.project_id,
        task_id=event.task_id,
        event_type=event.event_type,
        actor_type=event.actor_type.value,
        actor_id=event.actor_id,
        payload=event.payload,
        created_at=event.created_at,
        idempotency_key=event.idempotency_key,
    )


def _audit_event(row: AuditEventRow) -> AuditEvent:
    return AuditEvent(
        event_id=row.event_id,
        project_id=row.project_id,
        task_id=row.task_id,
        event_type=row.event_type,
        actor_type=ActorType(row.actor_type),
        actor_id=row.actor_id,
        payload=dict(row.payload),
        created_at=row.created_at,
        idempotency_key=row.idempotency_key,
    )
