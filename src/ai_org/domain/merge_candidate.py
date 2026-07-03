from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from ai_org.domain.models import utc_now


class MergeCandidateStatus(StrEnum):
    WAITING_APPROVAL = "WAITING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    MERGED = "MERGED"
    BLOCKED = "BLOCKED"


class MergeCandidateSourceType(StrEnum):
    MOCK = "mock"
    DRY_RUN = "dry_run"
    MANUAL_FIXTURE = "manual_fixture"
    REAL_CODEX_BLOCKED_FIXTURE = "real_codex_blocked_fixture"


class MergeResultStatus(StrEnum):
    MERGED = "MERGED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


@dataclass(slots=True)
class MergeCandidate:
    candidate_id: str
    project_id: str
    task_id: str
    worker_run_id: str
    source_type: MergeCandidateSourceType
    base_commit: str
    changed_files: list[str]
    diff_summary: str
    patch_artifact_uri: str
    tests_summary: str
    review_decision: str
    candidate_branch: str | None = None
    worktree_uri: str | None = None
    requires_human_merge_approval: bool = True
    auto_merge: bool = False
    auto_push: bool = False
    status: MergeCandidateStatus = MergeCandidateStatus.WAITING_APPROVAL
    created_at: datetime = field(default_factory=utc_now)
    approved_at: datetime | None = None
    approved_by: str | None = None
    approval_reason: str | None = None
    version: int = 0


@dataclass(slots=True)
class MergeResult:
    result_id: str
    candidate_id: str
    status: MergeResultStatus
    summary: str
    tests_passed: bool
    auto_push: bool = False
    auto_deploy: bool = False
    integration_worktree_uri: str | None = None
    created_at: datetime = field(default_factory=utc_now)
