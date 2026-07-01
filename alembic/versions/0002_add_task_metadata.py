from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_add_task_metadata"
down_revision = "0001_initial_business_schema"
branch_labels = None
depends_on = None

AI_ORG_SCHEMA = "ai_org"


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        schema=AI_ORG_SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("tasks", "metadata", schema=AI_ORG_SCHEMA)
