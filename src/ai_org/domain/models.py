from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from ai_org.domain.enums import (
    ActorType,
    ApprovalStatus,
    ProjectStatus,
    RiskLevel,
    TaskStatus,
    WorkerRunStatus,
)


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


@dataclass(slots=True)
class Project:
    project_id: str
    title: str
    goal: str
    status: ProjectStatus
    success_criteria: list[str]
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    version: int = 0
    idempotency_key: str | None = None


@dataclass(slots=True)
class Task:
    task_id: str
    project_id: str
    title: str
    objective: str
    worker_type: str
    status: TaskStatus
    risk_level: RiskLevel
    dependencies: list[str]
    acceptance_criteria: list[str]
    attempt_count: int = 0
    max_attempts: int = 2
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    version: int = 0
    idempotency_key: str | None = None


@dataclass(slots=True)
class WorkerRun:
    run_id: str
    task_id: str
    worker_type: str
    status: WorkerRunStatus
    structured_input: dict[str, Any]
    structured_output: dict[str, Any] | None
    attempt_number: int
    idempotency_key: str
    started_at: datetime
    finished_at: datetime | None = None
    error: str | None = None
    version: int = 0


@dataclass(slots=True)
class Approval:
    approval_id: str
    project_id: str
    task_id: str
    action: str
    risk_level: RiskLevel
    status: ApprovalStatus
    request_payload: dict[str, Any]
    decision: str | None = None
    decision_reason: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    decided_at: datetime | None = None
    version: int = 0
    idempotency_key: str | None = None


@dataclass(slots=True)
class AuditEvent:
    event_id: str
    project_id: str | None
    task_id: str | None
    event_type: str
    actor_type: ActorType
    actor_id: str
    payload: dict[str, Any]
    created_at: datetime = field(default_factory=utc_now)
    idempotency_key: str | None = None
