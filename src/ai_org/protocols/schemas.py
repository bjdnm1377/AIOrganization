from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ai_org.domain.enums import (
    AgentResultStatus,
    ApprovalStatus,
    ProjectStatus,
    ReviewDecision,
    RiskLevel,
    TaskStatus,
    WorkerRunStatus,
    WorkerType,
)
from ai_org.domain.merge_candidate import (
    MergeCandidateSourceType,
    MergeCandidateStatus,
    MergeResultStatus,
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TaskSpec(StrictModel):
    title: str
    objective: str
    worker_type: WorkerType = WorkerType.RESEARCH
    risk_level: RiskLevel = RiskLevel.LOW
    dependencies: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=lambda: ["mock result reviewed"])
    max_attempts: int = Field(default=2, ge=1, le=5)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreateProjectRequest(StrictModel):
    title: str
    goal: str
    success_criteria: list[str] = Field(default_factory=lambda: ["all tasks accepted"])
    tasks: list[TaskSpec] = Field(default_factory=list)
    idempotency_key: str | None = None


class TaskResponse(StrictModel):
    task_id: str
    project_id: str
    title: str
    objective: str
    worker_type: str
    status: TaskStatus
    risk_level: RiskLevel
    dependencies: list[str]
    acceptance_criteria: list[str]
    metadata: dict[str, Any] = Field(default_factory=dict)
    attempt_count: int
    max_attempts: int
    created_at: datetime
    updated_at: datetime
    version: int


class ProjectResponse(StrictModel):
    project_id: str
    title: str
    goal: str
    status: ProjectStatus
    success_criteria: list[str]
    created_at: datetime
    updated_at: datetime
    version: int


class Artifact(StrictModel):
    name: str
    uri: str
    kind: str = "text"
    sha256: str | None = None


class WorkerTestRecord(StrictModel):
    name: str
    status: Literal["passed", "failed", "skipped"]
    details: str | None = None


class AgentResult(StrictModel):
    task_id: str
    status: AgentResultStatus
    summary: str
    artifacts: list[Artifact] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    tests_run: list[WorkerTestRecord] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CriteriaResult(StrictModel):
    criterion: str
    passed: bool
    notes: str


class ReviewReport(StrictModel):
    task_id: str
    decision: ReviewDecision
    criteria_results: list[CriteriaResult]
    defects: list[str] = Field(default_factory=list)
    rework_instructions: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class ApprovalRequest(StrictModel):
    approval_id: str
    project_id: str
    task_id: str
    action: str
    risk_level: RiskLevel
    status: ApprovalStatus
    request_payload: dict[str, Any]
    created_at: datetime


class ApprovalDecision(StrictModel):
    decision: Literal["APPROVED", "REJECTED"]
    decision_reason: str
    idempotency_key: str | None = None


class ApprovalResponse(StrictModel):
    approval_id: str
    project_id: str
    task_id: str
    action: str
    risk_level: RiskLevel
    status: ApprovalStatus
    request_payload: dict[str, Any]
    decision: str | None
    decision_reason: str | None
    created_at: datetime
    decided_at: datetime | None


class WorkerRunResponse(StrictModel):
    run_id: str
    task_id: str
    worker_type: str
    status: WorkerRunStatus
    structured_input: dict[str, Any]
    structured_output: dict[str, Any] | None
    attempt_number: int
    idempotency_key: str
    started_at: datetime
    finished_at: datetime | None
    error: str | None


class MergeCandidateResponse(StrictModel):
    candidate_id: str
    project_id: str
    task_id: str
    worker_run_id: str
    source_type: MergeCandidateSourceType
    base_commit: str
    candidate_branch: str | None
    worktree_uri: str | None
    changed_files: list[str]
    diff_summary: str
    patch_artifact_uri: str
    tests_summary: str
    review_decision: str
    requires_human_merge_approval: bool
    auto_merge: bool
    auto_push: bool
    status: MergeCandidateStatus
    created_at: datetime
    approved_at: datetime | None
    approved_by: str | None
    approval_reason: str | None


class MergeCandidateApprovalDecision(StrictModel):
    decision: Literal["APPROVED", "REJECTED"]
    decided_by: str
    reason: str


class MergeRequest(StrictModel):
    pass


class MergeResultResponse(StrictModel):
    result_id: str
    candidate_id: str
    status: MergeResultStatus
    summary: str
    tests_passed: bool
    auto_push: bool
    auto_deploy: bool
    integration_worktree_uri: str | None
    created_at: datetime


class AuditEventResponse(StrictModel):
    event_id: str
    project_id: str | None
    task_id: str | None
    event_type: str
    actor_type: str
    actor_id: str
    payload: dict[str, Any]
    created_at: datetime


class WorkflowStatus(StrictModel):
    project: ProjectResponse
    tasks: list[TaskResponse]
    approvals: list[ApprovalResponse] = Field(default_factory=list)
    worker_runs: list[WorkerRunResponse] = Field(default_factory=list)
    waiting_for_approval: bool = False


class ErrorResponse(StrictModel):
    code: str
    message: str
    request_id: str
