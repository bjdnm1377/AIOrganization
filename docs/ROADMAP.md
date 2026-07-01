# Roadmap

## Completed In This Stage

- Minimal domain model and state machine.
- Pydantic v2 protocol models.
- Worker port, WorkerRegistry, Mock Workers, and Codex dry-run worker.
- LangGraph workflow with low-risk execution and high-risk approval interrupt.
- In-memory persistence for default local API and tests.
- PostgreSQL SQLAlchemy models and Alembic business migration.
- Strict checkpoint serializer self-check.
- FastAPI control/query endpoints.
- Automated tests for core scenarios.

## Next Stage

Codex Coding Worker isolation execution:

- Codex adapter remains behind the Worker port.
- Use task-scoped Git worktrees.
- Add Docker-based execution isolation only after an explicit sandbox design.
- Capture changed files, command logs, test output, and review evidence.
- Keep approval gates for shell/network/file-system permission increases.

## Later Stages

- Real PostgreSQL runtime wiring in app startup.
- Checkpoint cleanup job.
- Permission and budget domain model.
- Artifact store.
- Real Review Worker policy checks.
- Optional OpenHands or other execution runtime only after a new ADR.
