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

Tests marked `postgres` require a real PostgreSQL database. They can run in two
modes:

- GitHub Actions service mode: set `AI_ORG_USE_EXISTING_POSTGRES=true`,
  `AI_ORG_DATABASE_URL`, and `AI_ORG_CHECKPOINT_DATABASE_URL`. This is the
  preferred CI path.
- Local Docker Compose mode: if `AI_ORG_USE_EXISTING_POSTGRES` is not set, the
  test attempts to start `docker-compose.yml`. If Docker is unavailable, it
  skips with a clear reason.

The PostgreSQL integration test runs Alembic, interrupts at approval, closes the
business session, recreates the repository/service/workflow, resumes from
PostgreSQL checkpoint, and verifies worker-run counts. A local skip must be
recorded as an environment limitation in acceptance reports.

## CI Verification

The GitHub Actions workflow is `.github/workflows/verification.yml`. It uses
Python 3.12 and a `postgres:16.6` service container, then runs:

```bash
python -m ruff format --check .
python -m ruff check .
python -m mypy src tests
python -m alembic upgrade head
python -m pytest tests/integration/test_alembic_and_postgres.py -q
python -m pytest tests/integration/test_workflow_scenarios.py -q
python -m pytest tests/e2e/test_api.py -q
python -m pytest tests/unit/test_checkpoint_security.py -q
python -m pytest -q
```

The workflow also verifies `requirements-lock.txt`, runs `pip-audit`, generates
a license report and CycloneDX SBOM, runs `detect-secrets`, and runs
`git diff --check`.

## External Services

Tests do not call real LLMs, Codex, OpenHands, paid services, or user-provided
untrusted code.

## Supply Chain Checks

```powershell
.\scripts\supply_chain_checks.ps1
```

The script writes generated reports under `reports/`, which is ignored by Git.
