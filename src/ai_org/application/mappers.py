from __future__ import annotations

import re

from ai_org.domain.merge_candidate import MergeCandidate, MergeResult
from ai_org.domain.models import Approval, AuditEvent, Project, Task, WorkerRun
from ai_org.protocols.schemas import (
    ApprovalResponse,
    AuditEventResponse,
    MergeCandidateResponse,
    MergeResultResponse,
    ProjectResponse,
    TaskResponse,
    WorkerRunResponse,
)
from ai_org.security import (
    POSIX_ABSOLUTE_PATH_RE,
    WINDOWS_ABSOLUTE_PATH_RE,
    redact,
    sensitive_pattern_count,
)

_GENERIC_POSIX_ABSOLUTE_RE = re.compile(r"(?m)(?:^|[\s\"'])/(?!dev/null\b)[A-Za-z0-9_.-]+/")


def project_to_response(project: Project) -> ProjectResponse:
    return ProjectResponse(
        project_id=project.project_id,
        title=project.title,
        goal=project.goal,
        status=project.status,
        success_criteria=project.success_criteria,
        created_at=project.created_at,
        updated_at=project.updated_at,
        version=project.version,
    )


def task_to_response(task: Task) -> TaskResponse:
    return TaskResponse(
        task_id=task.task_id,
        project_id=task.project_id,
        title=task.title,
        objective=task.objective,
        worker_type=task.worker_type,
        status=task.status,
        risk_level=task.risk_level,
        dependencies=task.dependencies,
        acceptance_criteria=task.acceptance_criteria,
        metadata=task.metadata,
        attempt_count=task.attempt_count,
        max_attempts=task.max_attempts,
        created_at=task.created_at,
        updated_at=task.updated_at,
        version=task.version,
    )


def approval_to_response(approval: Approval) -> ApprovalResponse:
    return ApprovalResponse(
        approval_id=approval.approval_id,
        project_id=approval.project_id,
        task_id=approval.task_id,
        action=approval.action,
        risk_level=approval.risk_level,
        status=approval.status,
        request_payload=approval.request_payload,
        decision=approval.decision,
        decision_reason=approval.decision_reason,
        created_at=approval.created_at,
        decided_at=approval.decided_at,
    )


def worker_run_to_response(run: WorkerRun) -> WorkerRunResponse:
    return WorkerRunResponse(
        run_id=run.run_id,
        task_id=run.task_id,
        worker_type=run.worker_type,
        status=run.status,
        structured_input=run.structured_input,
        structured_output=run.structured_output,
        attempt_number=run.attempt_number,
        idempotency_key=run.idempotency_key,
        started_at=run.started_at,
        finished_at=run.finished_at,
        error=run.error,
    )


def merge_candidate_to_response(candidate: MergeCandidate) -> MergeCandidateResponse:
    return MergeCandidateResponse(
        candidate_id=candidate.candidate_id,
        project_id=candidate.project_id,
        task_id=candidate.task_id,
        worker_run_id=candidate.worker_run_id,
        source_type=candidate.source_type,
        base_commit=_api_safe_text(candidate.base_commit),
        candidate_branch=_api_safe_optional_text(candidate.candidate_branch),
        worktree_uri=_api_safe_optional_text(candidate.worktree_uri),
        changed_files=_api_safe_list(candidate.changed_files),
        diff_summary=_api_safe_text(candidate.diff_summary),
        patch_artifact_uri=_api_safe_text(candidate.patch_artifact_uri),
        tests_summary=_api_safe_text(candidate.tests_summary),
        review_decision=_api_safe_text(candidate.review_decision),
        requires_human_merge_approval=candidate.requires_human_merge_approval,
        auto_merge=candidate.auto_merge,
        auto_push=candidate.auto_push,
        status=candidate.status,
        created_at=candidate.created_at,
        approved_at=candidate.approved_at,
        approved_by=_api_safe_optional_text(candidate.approved_by),
        approval_reason=_api_safe_optional_text(candidate.approval_reason),
    )


def merge_result_to_response(result: MergeResult) -> MergeResultResponse:
    return MergeResultResponse(
        result_id=result.result_id,
        candidate_id=result.candidate_id,
        status=result.status,
        summary=result.summary,
        tests_passed=result.tests_passed,
        auto_push=result.auto_push,
        auto_deploy=result.auto_deploy,
        integration_worktree_uri=result.integration_worktree_uri,
        created_at=result.created_at,
    )


def audit_event_to_response(event: AuditEvent) -> AuditEventResponse:
    return AuditEventResponse(
        event_id=event.event_id,
        project_id=event.project_id,
        task_id=event.task_id,
        event_type=event.event_type,
        actor_type=event.actor_type.value,
        actor_id=event.actor_id,
        payload=event.payload,
        created_at=event.created_at,
    )


def _api_safe_optional_text(value: str | None) -> str | None:
    return None if value is None else _api_safe_text(value)


def _api_safe_list(values: list[str]) -> list[str]:
    return [_api_safe_text(value) for value in values]


def _api_safe_text(value: str) -> str:
    text = " ".join(str(redact(value)).split())
    if sensitive_pattern_count(text):
        return "[REDACTED]"
    if (
        WINDOWS_ABSOLUTE_PATH_RE.search(text)
        or POSIX_ABSOLUTE_PATH_RE.search(text)
        or _GENERIC_POSIX_ABSOLUTE_RE.search(text)
    ):
        return "<path>"
    return text
