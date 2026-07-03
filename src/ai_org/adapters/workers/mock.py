from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ai_org.adapters.codex.clients import DryRunCodexClient
from ai_org.adapters.codex.worker import CodexWorker
from ai_org.domain.enums import AgentResultStatus, ReviewDecision, WorkerType
from ai_org.domain.models import Task
from ai_org.ports.workers import ReviewWorker, Worker, WorkerRegistry, WorkerRequest
from ai_org.protocols.schemas import (
    AgentResult,
    Artifact,
    CriteriaResult,
    ReviewReport,
    WorkerTestRecord,
)


class MockResearchWorker:
    worker_type = WorkerType.RESEARCH.value

    def run(self, request: WorkerRequest) -> AgentResult:
        return _mock_result(request, "Mock research completed")


class MockCodingWorker:
    worker_type = WorkerType.CODING.value

    def run(self, request: WorkerRequest) -> AgentResult:
        return _mock_result(request, "Mock coding completed without shell execution")


class MockDocumentWorker:
    worker_type = WorkerType.DOCUMENT.value

    def run(self, request: WorkerRequest) -> AgentResult:
        return _mock_result(request, "Mock document completed")


class CodexDryRunWorker:
    worker_type = WorkerType.CODEX.value

    def run(self, request: WorkerRequest) -> AgentResult:
        return AgentResult(
            task_id=request.task.task_id,
            status=AgentResultStatus.DRY_RUN,
            summary="Codex worker is configured as dry-run only in this stage.",
            artifacts=[],
            evidence=["No real Codex process was started."],
            tests_run=[WorkerTestRecord(name="codex-dry-run", status="skipped")],
            assumptions=["Real Codex integration is intentionally disabled."],
            risks=[],
            unresolved_questions=[],
            metadata={
                "worker_type": self.worker_type,
                "coding_worker": True,
                "codex_mode": "dry_run",
                "dry_run": True,
                "changed_files": [],
                "policy_violations": [],
                "no_real_codex_started": True,
            },
        )


class MockReviewWorker:
    worker_type = WorkerType.REVIEW.value

    def review(self, task: Task, result: AgentResult, attempt_number: int) -> ReviewReport:
        if "force_rework" in task.acceptance_criteria:
            return ReviewReport(
                task_id=task.task_id,
                decision=ReviewDecision.REWORK_REQUIRED,
                criteria_results=[
                    CriteriaResult(
                        criterion="force_rework",
                        passed=False,
                        notes="Test scenario requested deterministic rework.",
                    )
                ],
                defects=["Deterministic rework requested by task acceptance criteria."],
                rework_instructions=["Retry until max_attempts stops the loop."],
                confidence=0.95,
            )
        coding_report = _review_coding_result(task, result, attempt_number)
        if coding_report is not None:
            return coding_report
        passed = result.status in {
            AgentResultStatus.SUCCEEDED,
            AgentResultStatus.DRY_RUN,
            AgentResultStatus.NOT_CONFIGURED,
        }
        return ReviewReport(
            task_id=task.task_id,
            decision=ReviewDecision.ACCEPTED if passed else ReviewDecision.REJECTED,
            criteria_results=[
                CriteriaResult(
                    criterion=criterion,
                    passed=passed,
                    notes="Reviewed by independent MockReviewWorker.",
                )
                for criterion in task.acceptance_criteria
            ],
            defects=[] if passed else ["Worker result did not succeed."],
            rework_instructions=[] if passed else ["Fix worker result and retry."],
            confidence=0.9,
        )


def _mock_result(request: WorkerRequest, summary: str) -> AgentResult:
    return AgentResult(
        task_id=request.task.task_id,
        status=AgentResultStatus.SUCCEEDED,
        summary=f"{summary}: {request.task.objective}",
        artifacts=[
            Artifact(
                name=f"{request.task.task_id}-artifact",
                uri=f"memory://artifacts/{request.task.task_id}/{request.attempt_number}",
            )
        ],
        evidence=[f"deterministic-evidence:{request.task.task_id}:{request.attempt_number}"],
        tests_run=[WorkerTestRecord(name="mock-worker-deterministic-check", status="passed")],
        assumptions=["Mock worker does not call external services."],
        risks=[],
        unresolved_questions=[],
        metadata={
            "attempt_number": request.attempt_number,
            "worker_type": request.task.worker_type,
        },
    )


@dataclass(slots=True)
class DefaultWorkerRegistry(WorkerRegistry):
    workers: dict[str, Worker]
    review_worker: ReviewWorker

    @classmethod
    def create(cls, repo_root: str | Path | None = None) -> DefaultWorkerRegistry:
        root = Path(repo_root or Path.cwd()).resolve()
        workers: dict[str, Worker] = {
            WorkerType.RESEARCH.value: MockResearchWorker(),
            WorkerType.CODING.value: MockCodingWorker(),
            WorkerType.DOCUMENT.value: MockDocumentWorker(),
            WorkerType.CODEX.value: _build_codex_worker(root),
        }
        return cls(workers=workers, review_worker=MockReviewWorker())

    def get_worker(self, worker_type: str) -> Worker:
        try:
            return self.workers[worker_type]
        except KeyError as exc:
            raise KeyError(f"Worker {worker_type!r} is not registered") from exc

    def get_review_worker(self) -> ReviewWorker:
        return self.review_worker


def _review_coding_result(
    task: Task, result: AgentResult, attempt_number: int
) -> ReviewReport | None:
    if result.metadata.get("coding_worker") is not True:
        return None
    policy_violations = _string_list(result.metadata.get("policy_violations"))
    failed_tests = [record.name for record in result.tests_run if record.status == "failed"]
    not_configured = result.status == AgentResultStatus.NOT_CONFIGURED
    runtime_blocked = result.metadata.get("blocked_reason") in {
        "CODEX_CLI_TIMEOUT",
        "CODEX_STEP_TIMEOUT",
    }
    if policy_violations or not_configured or runtime_blocked:
        defects = policy_violations.copy()
        if not_configured:
            defects.append("codex:not_configured")
        if runtime_blocked:
            defects.append("codex:timeout")
        return ReviewReport(
            task_id=task.task_id,
            decision=ReviewDecision.REJECTED,
            criteria_results=[
                CriteriaResult(
                    criterion="coding_worker_policy",
                    passed=False,
                    notes="Coding Worker result violated isolation or configuration policy.",
                )
            ],
            defects=defects,
            rework_instructions=["Resolve policy violations before another attempt."],
            confidence=0.96,
        )
    merge_candidate_defects = _merge_candidate_defects(result.metadata.get("merge_candidate"))
    if merge_candidate_defects:
        return ReviewReport(
            task_id=task.task_id,
            decision=ReviewDecision.REJECTED,
            criteria_results=[
                CriteriaResult(
                    criterion="merge_candidate_approval_boundary",
                    passed=False,
                    notes="MergeCandidate summary must not perform merge, push, or approval.",
                )
            ],
            defects=merge_candidate_defects,
            rework_instructions=["Return only a pending human-approval merge candidate summary."],
            confidence=0.97,
        )
    if failed_tests:
        return ReviewReport(
            task_id=task.task_id,
            decision=ReviewDecision.REWORK_REQUIRED,
            criteria_results=[
                CriteriaResult(
                    criterion="coding_worker_tests",
                    passed=False,
                    notes="One or more deterministic coding checks failed.",
                )
            ],
            defects=[f"test_failed:{name}" for name in failed_tests],
            rework_instructions=["Fix failed checks and retry within max_attempts."],
            confidence=0.9,
        )
    passed = result.status in {AgentResultStatus.SUCCEEDED, AgentResultStatus.DRY_RUN}
    return ReviewReport(
        task_id=task.task_id,
        decision=ReviewDecision.ACCEPTED if passed else ReviewDecision.REJECTED,
        criteria_results=[
            CriteriaResult(
                criterion=criterion,
                passed=passed,
                notes="Coding Worker output reviewed independently by MockReviewWorker.",
            )
            for criterion in task.acceptance_criteria
        ],
        defects=[] if passed else ["Coding Worker result was not successful."],
        rework_instructions=[] if passed else ["Produce a successful structured result."],
        confidence=0.91,
    )


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _merge_candidate_defects(value: object) -> list[str]:
    if not isinstance(value, dict):
        return []
    defects: list[str] = []
    for key in ("merge_performed", "auto_merge", "auto_push"):
        if value.get(key) is not False:
            defects.append(f"merge_candidate:{key}_not_false")
    if value.get("human_approval_required") is not True:
        defects.append("merge_candidate:human_approval_not_required")
    if value.get("requires_human_merge_approval", True) is not True:
        defects.append("merge_candidate:requires_human_merge_approval_not_true")
    if value.get("approval_state") != "waiting_merge_approval":
        defects.append("merge_candidate:not_waiting_merge_approval")
    return defects


def _build_codex_worker(repo_root: Path) -> Worker:
    try:
        return CodexWorker(repo_root, client=DryRunCodexClient())
    except ValueError:
        return CodexDryRunWorker()
