from __future__ import annotations

from enum import StrEnum


class ProjectStatus(StrEnum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    REVIEWING = "REVIEWING"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


class TaskStatus(StrEnum):
    PENDING = "PENDING"
    READY = "READY"
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    REVIEWING = "REVIEWING"
    ACCEPTED = "ACCEPTED"
    REWORK_REQUIRED = "REWORK_REQUIRED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


class WorkerRunStatus(StrEnum):
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class ApprovalStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class RiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class WorkerType(StrEnum):
    RESEARCH = "research"
    CODING = "coding"
    DOCUMENT = "document"
    REVIEW = "review"
    CODEX = "codex"


class AgentResultStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    DRY_RUN = "DRY_RUN"


class ReviewDecision(StrEnum):
    ACCEPTED = "ACCEPTED"
    REWORK_REQUIRED = "REWORK_REQUIRED"
    REJECTED = "REJECTED"


class ActorType(StrEnum):
    SYSTEM = "SYSTEM"
    USER = "USER"
    WORKER = "WORKER"
    REVIEWER = "REVIEWER"
