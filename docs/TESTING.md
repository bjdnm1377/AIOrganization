# Testing

## Test Categories

- Pydantic protocol validation.
- Domain state transitions.
- Task dependency readiness.
- WorkerRegistry behavior.
- Approval policy and rejection.
- Retry and rework limits.
- Idempotency.
- In-memory repository behavior.
- Alembic migration file presence and schema intent.
- FastAPI endpoint behavior.
- LangGraph interrupt/resume behavior.
- Strict msgpack startup self-check.
- Illegal checkpoint state rejection.
- Sensitive field non-disclosure in API errors.

## Commands

```powershell
.\.venv\Scripts\python -m ruff format .
.\.venv\Scripts\python -m ruff check .
.\.venv\Scripts\python -m mypy src tests
.\.venv\Scripts\python -m pytest -q
```

## PostgreSQL Integration

Tests marked `postgres` and `docker` require Docker. If Docker is unavailable,
they skip with a clear reason. This is intentional and must be recorded as a
partial environment limitation in acceptance reports.

When Docker is available, the PostgreSQL integration test starts Docker Compose,
runs Alembic, interrupts at approval, closes the business session, recreates the
repository/service/workflow, resumes from PostgreSQL checkpoint, and verifies the
worker executes once.

## External Services

Tests do not call real LLMs, Codex, OpenHands, paid services, or user-provided
untrusted code.

## Supply Chain Checks

```powershell
.\scripts\supply_chain_checks.ps1
```

The script writes generated reports under `reports/`, which is ignored by Git.
