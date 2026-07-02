from __future__ import annotations

from dataclasses import replace

from ai_org.adapters.memory.repositories import InMemoryRepository
from ai_org.adapters.workers.mock import DefaultWorkerRegistry, MockReviewWorker
from ai_org.application.service import ProjectApplicationService
from ai_org.domain.enums import (
    AgentResultStatus,
    ReviewDecision,
    TaskStatus,
    WorkerRunStatus,
    WorkerType,
)
from ai_org.domain.models import WorkerRun, utc_now
from ai_org.protocols.schemas import (
    AgentResult,
    CreateProjectRequest,
    CriteriaResult,
    ReviewReport,
    TaskSpec,
    WorkerTestRecord,
)


def test_accepted_codex_result_creates_merge_candidate_audit_event() -> None:
    repo = InMemoryRepository()
    service = ProjectApplicationService(
        repo,
        DefaultWorkerRegistry(workers={}, review_worker=MockReviewWorker()),
    )
    project = service.create_project(
        CreateProjectRequest(
            title="Merge candidate audit",
            goal="Record a human-reviewable merge candidate",
            tasks=[
                TaskSpec(
                    title="Code",
                    objective="Create merge candidate",
                    worker_type=WorkerType.CODEX,
                )
            ],
        )
    )
    task = repo.list_tasks(project.project_id)[0]
    repo.update_task(replace(task, status=TaskStatus.REVIEWING), expected_version=task.version)
    candidate = {
        "changed_files": ["docs/MERGE_APPROVAL.md"],
        "changed_file_count": 1,
        "diff_summary": "changed=1",
        "review_decision": "pending_review",
        "tests_passed": True,
        "merge_performed": False,
        "auto_merge": False,
        "auto_push": False,
        "human_approval_required": True,
        "approval_state": "waiting_merge_approval",
    }
    result = AgentResult(
        task_id=task.task_id,
        status=AgentResultStatus.SUCCEEDED,
        summary="Created merge candidate",
        tests_run=[WorkerTestRecord(name="unit", status="passed")],
        metadata={
            "coding_worker": True,
            "merge_candidate": candidate,
            "merge_candidate_artifact_uri": "artifact://codex/task/attempt-1/merge-candidate.json",
        },
    )
    repo.add_worker_run(
        WorkerRun(
            run_id="run_merge_candidate",
            task_id=task.task_id,
            worker_type=WorkerType.CODEX.value,
            status=WorkerRunStatus.SUCCEEDED,
            structured_input={},
            structured_output=result.model_dump(mode="json"),
            attempt_number=1,
            idempotency_key="worker:task:1:produce",
            started_at=utc_now(),
            finished_at=utc_now(),
        )
    )
    report = ReviewReport(
        task_id=task.task_id,
        decision=ReviewDecision.ACCEPTED,
        criteria_results=[
            CriteriaResult(criterion="merge candidate summary", passed=True, notes="accepted")
        ],
        confidence=0.91,
    )

    outcome = service.handle_review_decision(task.task_id, report)

    events = repo.list_audit_events(project.project_id)
    merge_events = [event for event in events if event.event_type == "merge_candidate.created"]
    assert outcome == "accepted"
    assert len(merge_events) == 1
    assert merge_events[0].payload["candidate"] == candidate
    assert merge_events[0].payload["artifact_uri"].startswith("artifact://codex/")
