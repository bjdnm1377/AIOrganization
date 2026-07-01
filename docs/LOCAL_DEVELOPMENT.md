# Local Development

## Environment

The project verification baseline is Python 3.12. The current implementation
host used Python 3.13 because Python 3.12 is not installed locally; this does
not change the project baseline.

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -r requirements-lock.txt
```

On a machine with Python 3.12 installed, prefer:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -r requirements-lock.txt
.\.venv\Scripts\python -m pip install -e .
```

## Run Checks

```powershell
.\.venv\Scripts\python -m ruff format .
.\.venv\Scripts\python -m ruff check .
.\.venv\Scripts\python -m mypy src tests
.\.venv\Scripts\python -m pytest -q
```

## Run API

```powershell
.\.venv\Scripts\python -m uvicorn ai_org.adapters.api.main:create_app --factory --reload
```

## PostgreSQL

Docker Compose file: `docker-compose.yml`.

```powershell
$env:AI_ORG_POSTGRES_PASSWORD = Read-Host "Local PostgreSQL password"
docker compose up -d postgres
```

The local Compose image is fixed to `postgres:16.6`. If Docker is missing,
PostgreSQL integration tests skip explicitly. The local host for this stage did
not have Docker installed.

To run the API against PostgreSQL after migrations:

```powershell
$env:AI_ORG_POSTGRES_PASSWORD = Read-Host "Local PostgreSQL password"
$env:AI_ORG_DATABASE_URL = "postgresql+psycopg://ai_org_app:${env:AI_ORG_POSTGRES_PASSWORD}@localhost:5432/ai_org"
$env:AI_ORG_CHECKPOINT_SETUP = "true"
.\.venv\Scripts\python -m uvicorn ai_org.adapters.api.main:create_app --factory --reload
```

Use `AI_ORG_CHECKPOINT_SETUP=true` only for first-time local initialization or
tests. Runtime roles should use pre-created checkpoint tables.

## GitHub Actions Verification

When local Python 3.12 or Docker is unavailable, use the repository workflow:

```text
.github/workflows/verification.yml
```

The workflow provisions Python 3.12 and a PostgreSQL service container, verifies
the lock file, runs Alembic, exercises PostgreSQL checkpoint recovery, runs the
full test suite, and produces supply-chain reports. Until that workflow actually
passes, the project remains blocked from entering the Codex Coding Worker
isolation stage.

## Manual Real Codex Smoke

The default development loop does not call real Codex. To manually run the
controlled local smoke test on a machine with an authenticated Codex CLI:

```powershell
$env:AI_ORG_ENABLE_REAL_CODEX_SMOKE = "true"
.\.venv\Scripts\python -m pytest tests\manual\test_real_codex_smoke.py -q
```

The smoke test runs inside a temporary Git worktree, allows only `smoke/**`, and
does not commit or merge output. Default `pytest` collection excludes
`tests/manual`; the smoke test runs only when this file is invoked explicitly.

## No Secrets Required

Default tests and CI must not require `OPENAI_API_KEY`, Codex credentials, cloud
accounts, or paid services. The manual real Codex smoke test uses the local
Codex CLI session only when explicitly opted in.

## Supply Chain Reports

```powershell
.\scripts\supply_chain_checks.ps1
```

Generated files are written to `reports/` and are not committed.
