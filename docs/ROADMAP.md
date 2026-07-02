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
- Controlled local real Codex CLI smoke path with explicit opt-in, task
  worktree, smoke-only file policy, command-log sanitization, independent
  review, and manual test coverage.
- Docker sandbox foundation with SandboxRunner port, Mock and Docker adapters,
  default disabled network, mount/resource policy checks, fixed safe Docker
  integration tests, and optional CodexWorker sandbox smoke hook.
- Controlled real Codex small code-task path with separate opt-in, fixed
  allowed files, task worktree isolation, fixed DockerSandboxRunner validation,
  sanitized artifacts, independent review, no automatic merge, manual local
  validation, and GitHub Actions verification with real Codex disabled.

## Next Stage

Controlled multi-file code task and human merge approval:

- Keep Codex behind Worker and CodexClient ports.
- Preserve task-scoped Git worktrees and Review Worker gating.
- Route formatter/test/build commands through the sandbox runner by default.
- Keep approval gates for shell, network, and file-system permission increases.
- Continue to avoid untrusted user code and automatic merge until a later stage.
- Add a human approval boundary before any branch merge.

## Later Stages

- Production hardening for arbitrary Coding Worker execution.
- Checkpoint and worktree cleanup jobs.
- Permission and budget domain model.
- Artifact store and retention policy.
- Optional OpenHands or other execution runtime only after a new ADR.
