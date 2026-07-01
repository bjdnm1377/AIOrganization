from __future__ import annotations

from ai_org.domain.enums import ApprovalStatus, ProjectStatus, TaskStatus, WorkerRunStatus
from ai_org.domain.errors import InvalidTransitionError

PROJECT_TRANSITIONS: dict[ProjectStatus, set[ProjectStatus]] = {
    ProjectStatus.CREATED: {ProjectStatus.RUNNING, ProjectStatus.FAILED},
    ProjectStatus.RUNNING: {
        ProjectStatus.WAITING_APPROVAL,
        ProjectStatus.REVIEWING,
        ProjectStatus.COMPLETED,
        ProjectStatus.BLOCKED,
        ProjectStatus.FAILED,
    },
    ProjectStatus.WAITING_APPROVAL: {
        ProjectStatus.RUNNING,
        ProjectStatus.BLOCKED,
        ProjectStatus.FAILED,
    },
    ProjectStatus.REVIEWING: {
        ProjectStatus.RUNNING,
        ProjectStatus.COMPLETED,
        ProjectStatus.BLOCKED,
        ProjectStatus.FAILED,
    },
    ProjectStatus.COMPLETED: set(),
    ProjectStatus.BLOCKED: set(),
    ProjectStatus.FAILED: set(),
}

TASK_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.PENDING: {TaskStatus.READY, TaskStatus.BLOCKED, TaskStatus.FAILED},
    TaskStatus.READY: {
        TaskStatus.RUNNING,
        TaskStatus.WAITING_APPROVAL,
        TaskStatus.BLOCKED,
        TaskStatus.FAILED,
    },
    TaskStatus.RUNNING: {TaskStatus.REVIEWING, TaskStatus.FAILED, TaskStatus.BLOCKED},
    TaskStatus.WAITING_APPROVAL: {TaskStatus.READY, TaskStatus.BLOCKED, TaskStatus.FAILED},
    TaskStatus.REVIEWING: {
        TaskStatus.ACCEPTED,
        TaskStatus.REWORK_REQUIRED,
        TaskStatus.BLOCKED,
        TaskStatus.FAILED,
    },
    TaskStatus.REWORK_REQUIRED: {TaskStatus.RUNNING, TaskStatus.BLOCKED, TaskStatus.FAILED},
    TaskStatus.ACCEPTED: set(),
    TaskStatus.BLOCKED: set(),
    TaskStatus.FAILED: set(),
}

APPROVAL_TRANSITIONS: dict[ApprovalStatus, set[ApprovalStatus]] = {
    ApprovalStatus.PENDING: {ApprovalStatus.APPROVED, ApprovalStatus.REJECTED},
    ApprovalStatus.APPROVED: set(),
    ApprovalStatus.REJECTED: set(),
}

WORKER_RUN_TRANSITIONS: dict[WorkerRunStatus, set[WorkerRunStatus]] = {
    WorkerRunStatus.RUNNING: {
        WorkerRunStatus.SUCCEEDED,
        WorkerRunStatus.FAILED,
        WorkerRunStatus.SKIPPED,
    },
    WorkerRunStatus.SUCCEEDED: set(),
    WorkerRunStatus.FAILED: set(),
    WorkerRunStatus.SKIPPED: set(),
}


def ensure_project_transition(current: ProjectStatus, target: ProjectStatus) -> None:
    if target != current and target not in PROJECT_TRANSITIONS[current]:
        raise InvalidTransitionError(f"Project transition {current}->{target} is not allowed")


def ensure_task_transition(current: TaskStatus, target: TaskStatus) -> None:
    if target != current and target not in TASK_TRANSITIONS[current]:
        raise InvalidTransitionError(f"Task transition {current}->{target} is not allowed")


def ensure_approval_transition(current: ApprovalStatus, target: ApprovalStatus) -> None:
    if target != current and target not in APPROVAL_TRANSITIONS[current]:
        raise InvalidTransitionError(f"Approval transition {current}->{target} is not allowed")


def ensure_worker_run_transition(current: WorkerRunStatus, target: WorkerRunStatus) -> None:
    if target != current and target not in WORKER_RUN_TRANSITIONS[current]:
        raise InvalidTransitionError(f"WorkerRun transition {current}->{target} is not allowed")
