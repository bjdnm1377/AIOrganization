# Roadmap

## Completed

- Minimal domain model and state machine.
- Pydantic v2 protocol models.
- Worker port, WorkerRegistry, Mock Workers, and independent Review Worker.
- LangGraph workflow with low-risk execution and high-risk approval interrupt.
- In-memory persistence for default local API and tests.
- PostgreSQL SQLAlchemy models and Alembic migrations.
- Strict checkpoint serializer self-check.
- FastAPI control/query endpoints.
- GitHub Actions Python 3.12 and PostgreSQL verification.
- Codex Mock/DryRun Worker with task worktree isolation, diff/log artifacts,
  policy checks, independent review gating, API artifact metadata queries, and
  tests.

## Next Stage

Real Codex Worker controlled smoke test:

- Keep Codex behind Worker and CodexClient ports.
- Require explicit opt-in authentication and non-production repository scope.
- Preserve task-scoped Git worktrees and Review Worker gating.
- Do not add Docker-based untrusted execution until a sandbox design is approved.
- Keep approval gates for shell, network, and file-system permission increases.

## Later Stages

- Production sandbox for Coding Worker execution.
- Checkpoint and worktree cleanup jobs.
- Permission and budget domain model.
- Artifact store and retention policy.
- Optional OpenHands or other execution runtime only after a new ADR.
