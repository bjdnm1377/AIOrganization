from __future__ import annotations

from dataclasses import dataclass

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
            metadata={"worker_type": self.worker_type, "dry_run": True},
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
    def create(cls) -> DefaultWorkerRegistry:
        workers: dict[str, Worker] = {
            WorkerType.RESEARCH.value: MockResearchWorker(),
            WorkerType.CODING.value: MockCodingWorker(),
            WorkerType.DOCUMENT.value: MockDocumentWorker(),
            WorkerType.CODEX.value: CodexDryRunWorker(),
        }
        return cls(workers=workers, review_worker=MockReviewWorker())

    def get_worker(self, worker_type: str) -> Worker:
        try:
            return self.workers[worker_type]
        except KeyError as exc:
            raise KeyError(f"Worker {worker_type!r} is not registered") from exc

    def get_review_worker(self) -> ReviewWorker:
        return self.review_worker
