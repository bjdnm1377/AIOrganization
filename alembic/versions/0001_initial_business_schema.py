from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001_initial_business_schema"
down_revision = None
branch_labels = None
depends_on = None

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


def upgrade() -> None:
    op.execute(sa.text(f"create schema if not exists {AI_ORG_SCHEMA}"))
    op.execute(sa.text(f"create schema if not exists {CHECKPOINT_SCHEMA}"))
    op.create_table(
        "projects",
        sa.Column("project_id", sa.String(length=64), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("success_criteria", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.CheckConstraint(
            PROJECT_STATUS_CHECK,
            name="ck_projects_status",
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_projects_idempotency_key"),
        schema=AI_ORG_SCHEMA,
    )
    op.create_table(
        "tasks",
        sa.Column("task_id", sa.String(length=64), primary_key=True),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("worker_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("risk_level", sa.String(length=16), nullable=False),
        sa.Column("dependencies", sa.JSON(), nullable=False),
        sa.Column("acceptance_criteria", sa.JSON(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], [f"{AI_ORG_SCHEMA}.projects.project_id"]),
        sa.CheckConstraint(
            TASK_STATUS_CHECK,
            name="ck_tasks_status",
        ),
        sa.CheckConstraint("attempt_count >= 0", name="ck_tasks_attempt_count"),
        sa.CheckConstraint("max_attempts >= 1", name="ck_tasks_max_attempts"),
        schema=AI_ORG_SCHEMA,
    )
    op.create_index(
        "ix_tasks_project_status", "tasks", ["project_id", "status"], schema=AI_ORG_SCHEMA
    )
    op.create_table(
        "worker_runs",
        sa.Column("run_id", sa.String(length=64), primary_key=True),
        sa.Column("task_id", sa.String(length=64), nullable=False),
        sa.Column("worker_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("structured_input", sa.JSON(), nullable=False),
        sa.Column("structured_output", sa.JSON(), nullable=True),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["task_id"], [f"{AI_ORG_SCHEMA}.tasks.task_id"]),
        sa.CheckConstraint(
            "status in ('RUNNING','SUCCEEDED','FAILED','SKIPPED')", name="ck_worker_runs_status"
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_worker_runs_idempotency_key"),
        sa.UniqueConstraint(
            "task_id", "worker_type", "attempt_number", name="uq_worker_runs_task_worker_attempt"
        ),
        schema=AI_ORG_SCHEMA,
    )
    op.create_index(
        "ix_worker_runs_task_status", "worker_runs", ["task_id", "status"], schema=AI_ORG_SCHEMA
    )
    op.create_table(
        "approvals",
        sa.Column("approval_id", sa.String(length=64), primary_key=True),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("task_id", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("risk_level", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("request_payload", sa.JSON(), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("idempotency_key", sa.String(length=160), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], [f"{AI_ORG_SCHEMA}.projects.project_id"]),
        sa.ForeignKeyConstraint(["task_id"], [f"{AI_ORG_SCHEMA}.tasks.task_id"]),
        sa.CheckConstraint(
            "status in ('PENDING','APPROVED','REJECTED')", name="ck_approvals_status"
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_approvals_idempotency_key"),
        schema=AI_ORG_SCHEMA,
    )
    op.create_index(
        "ix_approvals_status_created", "approvals", ["status", "created_at"], schema=AI_ORG_SCHEMA
    )
    op.create_table(
        "audit_events",
        sa.Column("event_id", sa.String(length=64), primary_key=True),
        sa.Column("project_id", sa.String(length=64), nullable=True),
        sa.Column("task_id", sa.String(length=64), nullable=True),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("actor_type", sa.String(length=32), nullable=False),
        sa.Column("actor_id", sa.String(length=100), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=True),
        schema=AI_ORG_SCHEMA,
    )
    op.create_index(
        "ix_audit_project_created",
        "audit_events",
        ["project_id", "created_at"],
        schema=AI_ORG_SCHEMA,
    )


def downgrade() -> None:
    op.drop_index("ix_audit_project_created", table_name="audit_events", schema=AI_ORG_SCHEMA)
    op.drop_table("audit_events", schema=AI_ORG_SCHEMA)
    op.drop_index("ix_approvals_status_created", table_name="approvals", schema=AI_ORG_SCHEMA)
    op.drop_table("approvals", schema=AI_ORG_SCHEMA)
    op.drop_index("ix_worker_runs_task_status", table_name="worker_runs", schema=AI_ORG_SCHEMA)
    op.drop_table("worker_runs", schema=AI_ORG_SCHEMA)
    op.drop_index("ix_tasks_project_status", table_name="tasks", schema=AI_ORG_SCHEMA)
    op.drop_table("tasks", schema=AI_ORG_SCHEMA)
    op.drop_table("projects", schema=AI_ORG_SCHEMA)
    op.execute(sa.text(f"drop schema if exists {CHECKPOINT_SCHEMA}"))
    op.execute(sa.text(f"drop schema if exists {AI_ORG_SCHEMA}"))
