# Database Design

## Schemas

- `ai_org`: business tables.
- `langgraph_checkpoint`: planned LangGraph checkpoint tables.

Separate schemas keep business state logically separate from checkpoint recovery
state. The local default API uses an in-memory repository; PostgreSQL repository
code and Alembic migration files are present for integration environments.

## Business Tables

Migration: `alembic/versions/0001_initial_business_schema.py`

- `ai_org.projects`
- `ai_org.tasks`
- `ai_org.worker_runs`
- `ai_org.approvals`
- `ai_org.audit_events`

## Key Columns

All mutable business entities include `version` for optimistic locking. Updates
filter by the expected version and raise a conflict if no row is updated.

`worker_runs.idempotency_key` is unique. `approvals.idempotency_key` is unique
when present. `projects.idempotency_key` is unique when present.

## Transactions

`PostgresUnitOfWork` owns a SQLAlchemy session and commits on successful context
exit or rolls back on exceptions. The FastAPI PostgreSQL container also wires
session `commit` and `rollback` hooks into `ProjectApplicationService`, so each
mutating service operation has an explicit transaction boundary.

The in-memory default keeps no-op transaction hooks for deterministic local
tests.

## Checkpoint Tables

LangGraph checkpoint access is handled by `postgres_checkpointer()` in
`src/ai_org/orchestration/postgres_checkpoint.py`. Runtime access uses the
`langgraph_checkpoint` schema with the strict serializer. `setup=True` must be
passed only during initialization or tests because it may execute checkpoint DDL.
Runtime roles should use already-created checkpoint tables.

Live checkpoint PostgreSQL recovery could not be executed on this host because
Docker is not installed; the Docker-gated test executes it when Docker is
available.

## Retention

Business audit events are append-only. Checkpoint retention should be shorter
than business audit retention and can be cleaned after terminal project states
once recovery is no longer required. The cleanup job is documented but not yet
implemented in this stage.
