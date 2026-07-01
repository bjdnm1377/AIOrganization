from __future__ import annotations

from ai_org.domain.models import Approval, AuditEvent, Project, Task, WorkerRun
from ai_org.protocols.schemas import (
    ApprovalResponse,
    AuditEventResponse,
    ProjectResponse,
    TaskResponse,
    WorkerRunResponse,
)


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
