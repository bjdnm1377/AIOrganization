from __future__ import annotations

import pytest

from ai_org.application.merge_approval import (
    InMemoryMergeCandidateStore,
    MergeApprovalService,
)
from ai_org.domain.errors import ConflictError
from ai_org.domain.merge_candidate import MergeCandidateSourceType, MergeCandidateStatus
from ai_org.domain.models import AuditEvent


def test_create_merge_candidate_waits_for_human_approval() -> None:
    events: list[AuditEvent] = []
    service = _service(events)

    candidate = service.create_candidate(
        project_id="project-1",
        task_id="task-1",
        worker_run_id="run-1",
        source_type=MergeCandidateSourceType.MANUAL_FIXTURE,
        base_commit="abc123",
        changed_files=["tests/unit/example_test.py", "src/example.py"],
        diff_summary="small patch",
        patch_artifact_uri="artifact://merge-candidates/run-1.patch",
        tests_summary="pytest passed",
        review_decision="accepted",
        worktree_uri="worktree://fixture/run-1",
    )

    assert candidate.status == MergeCandidateStatus.WAITING_APPROVAL
    assert candidate.requires_human_merge_approval is True
    assert candidate.auto_merge is False
    assert candidate.auto_push is False
    assert candidate.review_decision == "ACCEPTED"
    assert candidate.changed_files == ["src/example.py", "tests/unit/example_test.py"]
    assert events[-1].event_type == "merge_candidate.waiting_approval"


def test_approval_requires_accepted_review_and_blocks_illegal_transitions() -> None:
    service = _service()
    rejected_by_review = service.create_candidate(
        project_id="project-1",
        task_id="task-1",
        worker_run_id="run-1",
        source_type=MergeCandidateSourceType.MOCK,
        base_commit="abc123",
        changed_files=["src/example.py"],
        diff_summary="small patch",
        patch_artifact_uri="artifact://merge-candidates/run-1.patch",
        tests_summary="pytest passed",
        review_decision="rejected",
    )

    with pytest.raises(ConflictError, match="has not passed review"):
        service.approve(
            rejected_by_review.candidate_id,
            approved_by="reviewer",
            approval_reason="not actually accepted",
        )

    accepted = service.create_candidate(
        project_id="project-1",
        task_id="task-2",
        worker_run_id="run-2",
        source_type=MergeCandidateSourceType.DRY_RUN,
        base_commit="abc123",
        changed_files=["src/example.py"],
        diff_summary="small patch",
        patch_artifact_uri="artifact://merge-candidates/run-2.patch",
        tests_summary="pytest passed",
        review_decision="accepted",
    )
    approved = service.approve(
        accepted.candidate_id,
        approved_by="reviewer",
        approval_reason="looks safe",
    )

    assert approved.status == MergeCandidateStatus.APPROVED
    assert approved.approved_by == "reviewer"
    with pytest.raises(ConflictError, match="not waiting approval"):
        service.approve(
            accepted.candidate_id,
            approved_by="reviewer",
            approval_reason="duplicate approval",
        )


def test_rejected_or_blocked_real_codex_fixture_cannot_be_approved() -> None:
    service = _service()
    rejected = service.create_candidate(
        project_id="project-1",
        task_id="task-1",
        worker_run_id="run-1",
        source_type=MergeCandidateSourceType.MANUAL_FIXTURE,
        base_commit="abc123",
        changed_files=["src/example.py"],
        diff_summary="small patch",
        patch_artifact_uri="artifact://merge-candidates/run-1.patch",
        tests_summary="pytest passed",
        review_decision="accepted",
    )
    rejected = service.reject(
        rejected.candidate_id,
        rejected_by="reviewer",
        rejection_reason="needs rework",
    )

    assert rejected.status == MergeCandidateStatus.REJECTED
    with pytest.raises(ConflictError, match="not waiting approval"):
        service.approve(
            rejected.candidate_id,
            approved_by="reviewer",
            approval_reason="changed mind",
        )

    blocked_real_codex = service.create_candidate(
        project_id="project-1",
        task_id="task-2",
        worker_run_id="run-2",
        source_type=MergeCandidateSourceType.REAL_CODEX_BLOCKED_FIXTURE,
        base_commit="abc123",
        changed_files=["src/example.py"],
        diff_summary="timeout fixture",
        patch_artifact_uri="artifact://merge-candidates/run-2.patch",
        tests_summary="not run",
        review_decision="accepted",
    )

    with pytest.raises(ConflictError, match="Blocked real Codex output"):
        service.approve(
            blocked_real_codex.candidate_id,
            approved_by="reviewer",
            approval_reason="not allowed",
        )


def _service(events: list[AuditEvent] | None = None) -> MergeApprovalService:
    if events is None:
        events = []
    return MergeApprovalService(InMemoryMergeCandidateStore(), events.append)
