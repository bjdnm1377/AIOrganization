# Local Development

## Environment

The implementation host used Python 3.13. The project supports
`>=3.12,<3.15`.

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -r requirements-lock.txt
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
docker compose up -d postgres
```

If Docker is missing, PostgreSQL integration tests skip explicitly. The local
host for this stage did not have Docker installed.

To run the API against PostgreSQL after migrations:

```powershell
$env:AI_ORG_POSTGRES_PASSWORD = Read-Host "Local PostgreSQL password"
$env:AI_ORG_DATABASE_URL = "postgresql+psycopg://ai_org_app:${env:AI_ORG_POSTGRES_PASSWORD}@localhost:5432/ai_org"
$env:AI_ORG_CHECKPOINT_SETUP = "true"
.\.venv\Scripts\python -m uvicorn ai_org.adapters.api.main:create_app --factory --reload
```

Use `AI_ORG_CHECKPOINT_SETUP=true` only for first-time local initialization or
tests. Runtime roles should use pre-created checkpoint tables.

## No Secrets Required

This stage must not require `OPENAI_API_KEY`, Codex credentials, cloud accounts,
or paid services.

## Supply Chain Reports

```powershell
.\scripts\supply_chain_checks.ps1
```

Generated files are written to `reports/` and are not committed.
