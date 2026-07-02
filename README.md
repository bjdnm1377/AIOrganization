# AI Organization

AI Organization is a two-layer AI organization skeleton. It implements a minimal
end-to-end workflow with deterministic Mock Workers, a Mock/DryRun Codex Coding
Worker adapter, explicitly opt-in local Codex CLI smoke and small code-task
paths, an explicitly opt-in controlled multi-file Codex task path that creates
a human-reviewable merge candidate, a Docker sandbox foundation for fixed safe
command tests, review, approvals, audit events, FastAPI query endpoints,
PostgreSQL mappings, Alembic migrations, and strict LangGraph checkpoint
serialization checks.

Default tests and CI do not call real LLMs, real Codex, OpenHands, Virtuoso,
HFSS, MATLAB, Redis, Temporal, or user-provided untrusted code. Real Codex CLI
execution exists only for controlled manual tests and requires explicit opt-in.

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
`MockCodexClient` and `DryRunCodexClient`.

`LocalCodexCliClient` can run a real local Codex CLI smoke task only when all of
the following are true:

- `AI_ORG_ENABLE_REAL_CODEX_SMOKE=true` is set for the process.
- `codex --version` succeeds.
- `codex doctor --json` reports usable authentication.
- The task uses `codex_mode="local_cli"`.
- The task is limited to smoke files such as `smoke/**`.

The real smoke path uses `codex --sandbox workspace-write --ask-for-approval
on-request exec --json --cd <worktree> --color never -`, runs only inside a
task-scoped Git worktree, records logical artifact URIs, and does not commit,
merge, or modify the main branch.

The small real code-task path is separately gated by
`AI_ORG_ENABLE_REAL_CODEX_CODE_TASK=true` and `codex_mode="local_code_task"`.
It is limited to:

- `src/ai_org/adapters/codex/smoke_helpers.py`
- `tests/unit/test_codex_smoke_helpers.py`

The task runs through the normal WorkerRegistry, task worktree, diff/log
artifact collection, DockerSandboxRunner fixed test command, and independent
Review Worker. It still does not auto-commit, merge, push, or modify the main
branch.

The controlled real multi-file task path is separately gated by
`AI_ORG_ENABLE_REAL_CODEX_MULTI_FILE_TASK=true` and
`codex_mode="local_multi_file_task"`. It is limited to:

- `docs/MERGE_APPROVAL.md`
- `src/ai_org/adapters/codex/merge_candidate.py`
- `tests/unit/test_codex_merge_candidate.py`

This path creates a `merge-candidate` artifact and a
`merge_candidate.created` audit event after independent Review Worker
acceptance. The candidate status is `WAITING_MERGE_APPROVAL`; the system still
does not commit, merge, push, delete worktrees, or deploy.

## Docker Sandbox Foundation

The repository includes `SandboxRunner` ports plus Mock and Docker adapters for
future Coding Worker command execution. Docker sandbox tests run fixed safe
commands only; they do not execute user-provided code and do not call real
Codex. The Docker runner defaults to a non-root user, `--cap-drop ALL`,
`no-new-privileges`, read-only root filesystem, explicit tmpfs, task-worktree
mount only, disabled network, and CPU/memory/PID/time/output limits.

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

Manual real Codex smoke test:

```powershell
$env:AI_ORG_ENABLE_REAL_CODEX_SMOKE = "true"
.\.venv\Scripts\python -m pytest tests\manual\test_real_codex_smoke.py -q
```

Do not run the manual smoke test in CI or without an intentionally configured
local Codex CLI session.

Manual real Codex small code task:

```powershell
$env:AI_ORG_ENABLE_REAL_CODEX_CODE_TASK = "true"
.\.venv\Scripts\python -m pytest tests\manual\test_real_codex_code_task.py -q
```

This test also requires Docker to be available. It is skipped by default and is
not part of CI.

Manual real Codex multi-file merge candidate task:

```powershell
$env:AI_ORG_ENABLE_REAL_CODEX_MULTI_FILE_TASK = "true"
.\.venv\Scripts\python -m pytest tests\manual\test_real_codex_multi_file_task.py -q
```

This test also requires Docker and a ready local Codex CLI session. It is
skipped by default and is not part of CI.
