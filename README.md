# AI Organization

AI Organization is a two-layer AI organization skeleton. It implements a minimal
end-to-end workflow with deterministic Mock Workers, a Mock/DryRun Codex Coding
Worker adapter, review, approvals, audit events, FastAPI query endpoints,
PostgreSQL mappings, Alembic migrations, and strict LangGraph checkpoint
serialization checks.

This repository currently does not call real LLMs, real Codex, OpenHands,
Virtuoso, HFSS, MATLAB, Redis, Temporal, or user-provided untrusted code.

## Quick Start

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -r requirements-lock.txt
.\.venv\Scripts\python -m pytest -q
```

Project metadata supports Python `>=3.12,<3.15`. GitHub Actions verifies the
Python 3.12 baseline. If Python 3.12 is unavailable locally, use CI as the
baseline verification source.

## Run The API

```powershell
.\.venv\Scripts\python -m uvicorn ai_org.adapters.api.main:create_app --factory --reload
```

Useful endpoints:

- `GET /health`
- `POST /projects`
- `POST /projects/{project_id}/run`
- `GET /projects/{project_id}/status`
- `GET /projects/{project_id}/worker-runs`
- `GET /worker-runs/{run_id}/artifacts`
- `POST /approvals/{approval_id}/decision`

## Codex Worker

Use `worker_type="codex"` with task metadata such as `codex_mode`,
`allowed_files`, `forbidden_files`, and `required_tests`. Default tests use only
`MockCodexClient` and `DryRunCodexClient`; real Codex execution is not enabled in
this stage.

## PostgreSQL

Business tables are defined in SQLAlchemy and Alembic under schema `ai_org`.
LangGraph checkpoint tables use schema `langgraph_checkpoint`. Docker Compose is
provided only for local PostgreSQL integration testing.

## Development Checks

```powershell
.\.venv\Scripts\python -m ruff format .
.\.venv\Scripts\python -m ruff check .
.\.venv\Scripts\python -m mypy src tests
.\.venv\Scripts\python -m pytest -q
```
