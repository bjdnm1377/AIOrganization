# Acceptance Report - First Runnable Skeleton

Date: 2026-07-01

Stage: First runnable skeleton and minimal persistent workflow

Status: IMPLEMENTATION COMPLETE / CI PUSH BLOCKED

Superseded status note: the follow-up CI verification stage is recorded in
`FINAL_VERIFICATION_REPORT.md`, `CI_PENDING_REPORT.md`, and
`CI_BLOCKED_REPORT.md`.

The project must not enter the Codex Coding Worker isolation stage yet. The
workflow `.github/workflows/verification.yml` is ready to run Python 3.12,
PostgreSQL service integration, Alembic migration, checkpoint recovery, tests,
and supply-chain scans, but the repository currently has no GitHub remote or
push authorization, so a real CI run has not yet been triggered or observed.

## 1. Stage Goal

Implement a runnable, testable, persistable minimal vertical workflow:

Create project -> create predefined task -> select ready task -> check risk ->
dispatch Mock Worker -> independent Review Worker -> update task status -> update
project status -> write audit records -> query through FastAPI.

High-risk tasks interrupt for approval, persist approval/checkpoint state, resume
after approval decision, and complete or block deterministically.

## 2. Actual Completion

- Python package skeleton under `src/ai_org`.
- Framework-free domain model, enums, errors, and transition guards.
- Pydantic v2 protocols:
  `CreateProjectRequest`, `ProjectResponse`, `TaskSpec`, `AgentResult`,
  `ReviewReport`, `ApprovalRequest`, `ApprovalDecision`, `WorkflowStatus`.
- Worker port, WorkerRegistry, deterministic Mock Workers, independent
  MockReviewWorker, and Codex dry-run worker.
- In-memory repository for no-key local tests.
- PostgreSQL SQLAlchemy models, repository, session helpers, and Alembic
  migration.
- FastAPI app factory that uses in-memory storage by default and switches to
  PostgreSQL when `AI_ORG_DATABASE_URL` is set.
- Explicit SQLAlchemy commit/rollback hooks for PostgreSQL service operations.
- LangGraph workflow with approval interrupt/resume and bounded rework loop.
- Strict checkpoint serializer setup with pickle fallback disabled.
- Docker-gated PostgreSQL checkpoint recovery test that recreates business
  session/service/workflow before resume when Docker is available.
- Supply-chain script for vulnerability, license, SBOM, and secret scans.
- Documentation for architecture, API, state machine, database, checkpoint
  security, local development, testing, threat model, and roadmap.

## 3. Not Completed / Environment Limits

- Live PostgreSQL integration test did not run on this host because `docker` is
  not installed.
- PostgreSQL database roles and grants are documented but not provisioned
  locally.
- Checkpoint cleanup/retention job is documented but not implemented.
- The lock file was generated under Python 3.13 because Python 3.12 is not
  installed on this host.
- No real LLM, real Codex, OpenHands, or untrusted-code sandbox is integrated in
  this stage by design.

## 4. Real File List

Key stage files:

- `.editorconfig`
- `.gitignore`
- `AGENTS.md`
- `README.md`
- `pyproject.toml`
- `requirements.in`
- `requirements-lock.txt`
- `docker-compose.yml`
- `scripts/supply_chain_checks.ps1`
- `alembic.ini`
- `alembic/env.py`
- `alembic/versions/0001_initial_business_schema.py`
- `src/ai_org/domain/enums.py`
- `src/ai_org/domain/errors.py`
- `src/ai_org/domain/models.py`
- `src/ai_org/domain/state_machine.py`
- `src/ai_org/protocols/schemas.py`
- `src/ai_org/ports/repositories.py`
- `src/ai_org/ports/workers.py`
- `src/ai_org/application/service.py`
- `src/ai_org/application/mappers.py`
- `src/ai_org/orchestration/checkpoint_security.py`
- `src/ai_org/orchestration/workflow.py`
- `src/ai_org/orchestration/postgres_checkpoint.py`
- `src/ai_org/adapters/memory/repositories.py`
- `src/ai_org/adapters/postgres/models.py`
- `src/ai_org/adapters/postgres/repositories.py`
- `src/ai_org/adapters/postgres/session.py`
- `src/ai_org/adapters/workers/mock.py`
- `src/ai_org/adapters/api/main.py`
- `tests/unit/test_protocols.py`
- `tests/unit/test_domain_state_machine.py`
- `tests/unit/test_worker_registry.py`
- `tests/unit/test_checkpoint_security.py`
- `tests/unit/test_architecture_boundaries.py`
- `tests/unit/test_memory_repository.py`
- `tests/integration/test_workflow_scenarios.py`
- `tests/integration/test_alembic_and_postgres.py`
- `tests/e2e/test_api.py`
- `docs/ARCHITECTURE_OVERVIEW.md`
- `docs/STATE_MACHINE.md`
- `docs/TASK_PROTOCOL.md`
- `docs/DATABASE_DESIGN.md`
- `docs/CHECKPOINT_SECURITY.md`
- `docs/API.md`
- `docs/LOCAL_DEVELOPMENT.md`
- `docs/TESTING.md`
- `docs/THREAT_MODEL.md`
- `docs/ROADMAP.md`

Generated but not committed:

- `reports/pip-audit-report.json`
- `reports/license-report.json`
- `reports/sbom.json`
- `reports/detect-secrets-report.json`

## 5. Core Architecture

Dependency direction:

FastAPI adapter -> Application service -> Domain + ports -> Repository/Worker
adapters.

LangGraph is isolated in `src/ai_org/orchestration`. The domain layer does not
import LangGraph, FastAPI, SQLAlchemy, or Alembic. Worker outputs are structured
Pydantic payloads, and the Review Worker is independent from the producing
worker.

## 6. Database Tables And Migrations

Migration:

- `alembic/versions/0001_initial_business_schema.py`

Business schema:

- `ai_org.projects`
- `ai_org.tasks`
- `ai_org.worker_runs`
- `ai_org.approvals`
- `ai_org.audit_events`

Checkpoint schema:

- `langgraph_checkpoint`

Runtime checkpoint access uses `postgres_checkpointer(..., setup=False)`. DDL is
only run when `setup=True`, which is reserved for initialization/tests.

## 7. API List

- `GET /health`
- `POST /projects`
- `GET /projects/{project_id}`
- `GET /projects/{project_id}/tasks`
- `POST /projects/{project_id}/run`
- `GET /projects/{project_id}/status`
- `GET /projects/{project_id}/approvals`
- `POST /approvals/{approval_id}/decision`
- `GET /projects/{project_id}/audit-events`

API errors are sanitized and do not expose database passwords, environment
variables, checkpoint binary payloads, or stack traces.

## 8. State Machine

Project states:

- `CREATED`
- `RUNNING`
- `WAITING_APPROVAL`
- `REVIEWING`
- `COMPLETED`
- `BLOCKED`
- `FAILED`

Task states:

- `PENDING`
- `READY`
- `RUNNING`
- `WAITING_APPROVAL`
- `REVIEWING`
- `ACCEPTED`
- `REWORK_REQUIRED`
- `BLOCKED`
- `FAILED`

Rework is bounded by `max_attempts`. Existing completed tasks are not executed
again. Existing RUNNING WorkerRuns with no structured output now raise a conflict
instead of re-executing the worker.

## 9. Checkpoint Security Implementation

- `LANGGRAPH_STRICT_MSGPACK=true` is configured before LangGraph imports.
- Pickle fallback is disabled.
- Serializer uses an explicit allowed msgpack module list.
- Startup self-check validates strict mode.
- Workflow state is restricted to primitive JSON-like values and serialized
  Pydantic payloads.
- Tests cover illegal checkpoint state rejection and pickle/unknown
  deserialization rejection.
- Database connections, file handles, locks, model clients, subprocess handles,
  and executable objects are not stored in checkpoint state.

## 10. Dependencies And Locked Versions

Direct runtime pins:

- `langgraph==1.2.7`
- `langgraph-checkpoint-postgres==3.1.0`
- `fastapi==0.138.2`
- `pydantic==2.13.4`
- `SQLAlchemy==2.0.51`
- `alembic==1.18.5`
- `psycopg[binary]==3.3.4`
- `uvicorn==0.49.0`
- `httpx==0.28.1`

Dev/test pins include `pytest==9.1.1`, `ruff==0.15.20`, `mypy==2.1.0`,
`pip-audit==2.10.1`, `pip-licenses==5.5.5`, `cyclonedx-bom==7.3.0`, and
`detect-secrets==1.5.0`.

`requirements-lock.txt` was generated from the local Python 3.13 environment.
Before production release, regenerate and verify the lock file under the selected
Python 3.12 baseline.

## 11. Automated Test Results

Latest commands:

- `.\.venv\Scripts\python -m ruff format .`
  - Exit code: 0
  - Result: `41 files left unchanged`
- `.\.venv\Scripts\python -m ruff check .`
  - Exit code: 0
  - Result: `All checks passed!`
- `.\.venv\Scripts\python -m mypy src tests`
  - Exit code: 0
  - Result: `Success: no issues found in 39 source files`
- `.\.venv\Scripts\python -m pytest -q`
  - Exit code: 0
  - Result: `27 passed, 1 skipped, 1 warning`

Skipped test:

- Docker/PostgreSQL integration test skipped because Docker is unavailable.

Docker commands:

- `docker --version`
  - Exit code: 1
  - Result: `docker` command not found
- `docker compose version`
  - Exit code: 1
  - Result: `docker` command not found

## 12. Supply Chain, License, Vulnerability, Secret Scan

Command:

- `.\scripts\supply_chain_checks.ps1`
  - Exit code: 0

Results:

- `pip-audit`: 106 dependencies audited, 0 known vulnerabilities.
- `pip-audit` skip: local editable package `ai-organization` is not on PyPI.
- `pip-licenses`: 103 package license entries generated.
- CycloneDX SBOM: 107 components generated.
- `detect-secrets`: 0 findings.

Generated reports are under `reports/` and are ignored by Git.

## 13. Reviewer Findings And Handling

Pre-implementation subagents:

- Architecture review agent.
- Database review agent.
- Testing review agent.
- Security review agent.

Final reviewer agent:

- Initial high findings:
  - FastAPI did not provide PostgreSQL persistence path.
  - PostgreSQL transaction boundaries were not explicit.
  - Existing RUNNING WorkerRun could be executed again.
  - PostgreSQL checkpoint recovery test did not recreate business session.
- Initial medium findings:
  - Checkpoint deserialization rejection test missing.
  - Checkpoint setup used runtime DDL by default.
  - Acceptance report was stale.

Resolution:

- Added PostgreSQL FastAPI container selected by `AI_ORG_DATABASE_URL`.
- Wired SQLAlchemy commit/rollback hooks into PostgreSQL service operations.
- Existing RUNNING production/review WorkerRuns now raise `ConflictError`.
- PostgreSQL Docker test now closes/recreates session/service/workflow before
  resume.
- Added checkpoint deserialization rejection tests.
- `postgres_checkpointer()` defaults to `setup=False`; setup DDL is explicit.
- This report was updated with real scan and verification results.

Reviewer re-check:

- Previous high/medium code findings resolved.
- Remaining issue was stale report content; fixed by this report update.

Residual low risks:

- PostgreSQL API container currently uses a long-lived SQLAlchemy session; a
  later concurrency hardening pass should move to session-per-request or
  session-per-workflow.
- Docker-gated PostgreSQL recovery is implemented but not locally executed
  without Docker.

## 14. Known Issues

- Live PostgreSQL integration not executed on this host because Docker is absent.
- PostgreSQL role provisioning and checkpoint cleanup are not implemented.
- No real Coding Worker sandbox is implemented in this stage.
- The FastAPI default remains in-memory when `AI_ORG_DATABASE_URL` is not set.

## 15. Risks

- Runtime PostgreSQL concurrency needs hardening before multi-user production.
- `psycopg[binary]` should be re-reviewed before binary redistribution.
- Python 3.12 lock verification is still required for the production baseline.

## 16. Next Stage Recommendation

Superseded by `FINAL_VERIFICATION_REPORT.md`: do not proceed to Codex Coding
Worker isolation execution until Python 3.12 lock verification and live
Docker/PostgreSQL integration complete in a suitable environment.

Original next-stage plan after environment unblock:

- Keep Codex behind the Worker port.
- Use task-scoped Git worktrees.
- Add Docker sandbox design and tests before executing real shell commands.
- Capture command logs, changed files, test output, and review evidence.
- Keep approval gates for permission increases.

## 17. Current Git Branch

- `master`

## 18. Stage Git Commit Hash

The stage commit is created after this report is finalized. The final response
records the immutable commit hash. A Git commit cannot embed its own final hash
inside tracked file content without changing that hash.

Base commit before this stage:

- `8fa56f4`

## 19. git status --short Result Before Commit

```text
 M .editorconfig
 M ACCEPTANCE_REPORT.md
 M docs/DECISIONS/ADR-001-agent-orchestration-framework.md
 M docs/DECISIONS/ADR-002-coding-worker-integration.md
 M docs/DEPENDENCY_EVALUATION.md
 M docs/DEPENDENCY_UPDATE_POLICY.md
 M docs/LICENSE_INVENTORY.md
 M docs/THIRD_PARTY_ARCHITECTURE.md
?? .gitignore
?? AGENTS.md
?? README.md
?? alembic.ini
?? alembic/
?? docker-compose.yml
?? docs/API.md
?? docs/ARCHITECTURE_OVERVIEW.md
?? docs/CHECKPOINT_SECURITY.md
?? docs/DATABASE_DESIGN.md
?? docs/LOCAL_DEVELOPMENT.md
?? docs/ROADMAP.md
?? docs/STATE_MACHINE.md
?? docs/TASK_PROTOCOL.md
?? docs/TESTING.md
?? docs/THREAT_MODEL.md
?? pyproject.toml
?? requirements-lock.txt
?? requirements.in
?? scripts/
?? src/
?? tests/
```

## 20. Key Git Diff Summary

- Added the Python application skeleton under `src/ai_org`.
- Added unit, integration, workflow, API, and Docker-gated PostgreSQL tests.
- Added Alembic migration and PostgreSQL SQLAlchemy adapter.
- Added FastAPI app with memory/PostgreSQL container modes.
- Added strict checkpoint security helper and tests.
- Added dependency pins, lock file, supply-chain script, and Docker Compose.
- Added required architecture, protocol, database, API, testing, security, and
  roadmap documentation.
- Converted Markdown files to UTF-8 with BOM to reduce Windows editor mojibake.

`git diff --check` exit code: 0.

## 21. User Acceptance Options

- Pass: CI has passed, enter Codex Coding Worker isolation execution stage.
- Wait: CI workflow is ready, wait for actual CI run result.
- Reject: continue fixing this CI verification stage.
- Pause: do not continue for now.
- Adjust goal: re-plan the next stage.
