# Database Design

## Schemas

- `ai_org`: business tables.
- `langgraph_checkpoint`: LangGraph checkpoint tables.

Separate schemas keep business state logically separate from checkpoint recovery
state.

## Migrations

- `alembic/versions/0001_initial_business_schema.py`
- `alembic/versions/0002_add_task_metadata.py`

## Business Tables

- `ai_org.projects`
- `ai_org.tasks`
- `ai_org.worker_runs`
- `ai_org.approvals`
- `ai_org.audit_events`

`tasks.metadata` stores structured execution constraints, including Codex
allowed files, forbidden files, allowed commands, required tests, and
Mock/DryRun options. Large diffs and logs are not stored directly in business
JSON fields; they are stored as artifact files with metadata persisted through
`WorkerRun.structured_output`.

## Concurrency And Idempotency

All mutable business entities include `version` for optimistic locking. Updates
filter by expected version and raise a conflict if no row is updated.

`worker_runs.idempotency_key` is unique. `approvals.idempotency_key` is unique
when present. `projects.idempotency_key` is unique when present.

## Transactions

PostgreSQL mode wires SQLAlchemy `commit` and `rollback` hooks into
`ProjectApplicationService`, so mutating service operations have explicit
transaction boundaries. The default in-memory repository keeps no-op hooks for
deterministic local tests.

## Checkpoint Tables

`postgres_checkpointer()` in `src/ai_org/orchestration/postgres_checkpoint.py`
uses the `langgraph_checkpoint` schema with the strict serializer. `setup=True`
must be used only during initialization or tests because it may execute
checkpoint DDL.

## Retention

Business audit events are append-only. Checkpoint retention should be shorter
than business audit retention and can be cleaned after terminal project states
once recovery is no longer required. Automatic cleanup is not implemented yet.
