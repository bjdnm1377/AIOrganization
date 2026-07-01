from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

AI_ORG_SCHEMA = "ai_org"
CHECKPOINT_SCHEMA = "langgraph_checkpoint"
PROJECT_STATUS_CHECK = (
    "status in ('CREATED','RUNNING','WAITING_APPROVAL','REVIEWING','COMPLETED','BLOCKED','FAILED')"
)
TASK_STATUS_CHECK = (
    "status in ("
    "'PENDING','READY','RUNNING','WAITING_APPROVAL','REVIEWING',"
    "'ACCEPTED','REWORK_REQUIRED','BLOCKED','FAILED'"
    ")"
)


class Base(DeclarativeBase):
    metadata = MetaData(schema=AI_ORG_SCHEMA)


class ProjectRow(Base):
    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint(
            PROJECT_STATUS_CHECK,
            name="ck_projects_status",
        ),
        UniqueConstraint("idempotency_key", name="uq_projects_idempotency_key"),
    )

    project_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    success_criteria: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)


class TaskRow(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint(
            TASK_STATUS_CHECK,
            name="ck_tasks_status",
        ),
        CheckConstraint("attempt_count >= 0", name="ck_tasks_attempt_count"),
        CheckConstraint("max_attempts >= 1", name="ck_tasks_max_attempts"),
    )

    task_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey(f"{AI_ORG_SCHEMA}.projects.project_id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    worker_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False)
    dependencies: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    acceptance_criteria: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)


class WorkerRunRow(Base):
    __tablename__ = "worker_runs"
    __table_args__ = (
        CheckConstraint(
            "status in ('RUNNING','SUCCEEDED','FAILED','SKIPPED')", name="ck_worker_runs_status"
        ),
        UniqueConstraint("idempotency_key", name="uq_worker_runs_idempotency_key"),
        UniqueConstraint(
            "task_id", "worker_type", "attempt_number", name="uq_worker_runs_task_worker_attempt"
        ),
    )

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    task_id: Mapped[str] = mapped_column(
        String(64), ForeignKey(f"{AI_ORG_SCHEMA}.tasks.task_id"), nullable=False, index=True
    )
    worker_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    structured_input: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    structured_output: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ApprovalRow(Base):
    __tablename__ = "approvals"
    __table_args__ = (
        CheckConstraint("status in ('PENDING','APPROVED','REJECTED')", name="ck_approvals_status"),
        UniqueConstraint("idempotency_key", name="uq_approvals_idempotency_key"),
    )

    approval_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey(f"{AI_ORG_SCHEMA}.projects.project_id"), nullable=False, index=True
    )
    task_id: Mapped[str] = mapped_column(
        String(64), ForeignKey(f"{AI_ORG_SCHEMA}.tasks.task_id"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    decision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    idempotency_key: Mapped[str | None] = mapped_column(String(160), nullable=True)


class AuditEventRow(Base):
    __tablename__ = "audit_events"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    task_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(160), nullable=True)
