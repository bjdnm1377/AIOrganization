# Testing

## Test Categories

- Pydantic protocol validation.
- Domain state transitions and task dependency readiness.
- WorkerRegistry behavior.
- Approval, rejection, retry, rework limit, and idempotency.
- In-memory repository behavior.
- Alembic migration and PostgreSQL repository/checkpoint recovery.
- FastAPI endpoint behavior.
- LangGraph interrupt/resume behavior.
- Strict msgpack startup self-check and illegal checkpoint state rejection.
- Sensitive field non-disclosure in API errors.
- Codex Worker Mock/DryRun behavior.
- Worktree creation, path traversal defense, and symlink-boundary defense.
- Coding Worker diff, artifact, command-log, review, rework, and idempotency.

## Local Commands

```powershell
.\.venv\Scripts\python -m ruff format .
.\.venv\Scripts\python -m ruff check .
.\.venv\Scripts\python -m mypy src tests
.\.venv\Scripts\python -m pytest -q
```

The implementation host currently uses Python 3.13 for local feedback. The
project baseline gate remains Python 3.12 in GitHub Actions.

## PostgreSQL Integration

Tests marked `postgres` run in two modes:

- GitHub Actions service mode with `AI_ORG_USE_EXISTING_POSTGRES=true`,
  `AI_ORG_DATABASE_URL`, and `AI_ORG_CHECKPOINT_DATABASE_URL`.
- Local Docker Compose mode when Docker is available.

If Docker is unavailable locally, PostgreSQL tests skip with a clear reason.
CI uses `postgres:16.6`.

## CI Verification

`.github/workflows/verification.yml` uses Python 3.12 and runs:

```bash
python -m ruff format --check .
python -m ruff check .
python -m mypy src tests
python -m alembic upgrade head
python -m pytest tests/integration/test_alembic_and_postgres.py -q
python -m pytest tests/integration/test_workflow_scenarios.py -q
python -m pytest tests/e2e/test_api.py -q
python -m pytest tests/unit/test_checkpoint_security.py -q
python -m pytest \
  tests/unit/test_worktree_service.py \
  tests/unit/test_codex_worker.py \
  tests/integration/test_codex_worker_workflow.py \
  tests/e2e/test_api.py \
  -q
python -m pytest -q
```

The workflow also verifies `requirements-lock.txt`, runs `pip-audit`, generates
a license report and CycloneDX SBOM, runs `detect-secrets`, and runs
`git diff --check`.

## External Services

Tests do not call real LLMs, real Codex, OpenHands, paid services, or
user-provided untrusted code. Codex Worker tests use only `MockCodexClient`,
`DryRunCodexClient`, and NOT_CONFIGURED `LocalCodexCliClient` behavior.
