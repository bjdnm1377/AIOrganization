# AI Organization

AI Organization is a two-layer AI organization skeleton. The current stage
implements a minimal end-to-end workflow with deterministic Mock Workers,
review, approvals, audit events, FastAPI query endpoints, PostgreSQL mappings,
Alembic migration files, and strict LangGraph checkpoint serialization checks.

This repository currently does not call real LLMs, real Codex, OpenHands,
Virtuoso, HFSS, MATLAB, Redis, Temporal, or user-provided untrusted code.

## Quick Start

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -r requirements-lock.txt
.\.venv\Scripts\python -m pytest
```

Project metadata supports Python `>=3.12,<3.15`. The implementation host only
had Python 3.13 available, so the local verification run used Python 3.13.

## Run The API

```powershell
.\.venv\Scripts\python -m uvicorn ai_org.adapters.api.main:create_app --factory --reload
```

Useful endpoints:

- `GET /health`
- `POST /projects`
- `POST /projects/{project_id}/run`
- `GET /projects/{project_id}/status`
- `POST /approvals/{approval_id}/decision`

## PostgreSQL

Business tables are defined in SQLAlchemy and Alembic under schema `ai_org`.
LangGraph checkpoint tables are planned under schema `langgraph_checkpoint`.
Docker Compose is provided only for local PostgreSQL integration testing. If
Docker is unavailable, PostgreSQL tests skip with an explicit reason.

## Development Checks

```powershell
.\.venv\Scripts\python -m ruff format .
.\.venv\Scripts\python -m ruff check .
.\.venv\Scripts\python -m mypy src tests
.\.venv\Scripts\python -m pytest -q
```
