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
- Local Codex CLI smoke opt-in, missing CLI, command construction, timeout, and
  failure behavior.
- Local Codex CLI small code-task opt-in, missing CLI, restricted command
  construction, fixed file scope, and Docker sandbox test-log behavior.
- Local Codex CLI multi-file task opt-in, missing CLI, restricted command
  construction, fixed file scope, MergeCandidate artifact creation, and Docker
  sandbox test-log behavior.
- Local real Codex main worktree modification detection and Review Worker
  rejection.
- Main-worktree fingerprint coverage for clean trees, tracked diffs, staged
  diffs, new untracked files, untracked file content changes, and dirty files
  whose status text does not change.
- Task-worktree symlink escape rejection and CI checks that real Codex remains
  disabled in GitHub Actions.
- MergeCandidate pure data shaping, local absolute path redaction, no merge,
  no auto-push, and application audit-event creation after accepted review.
- Worktree creation, path traversal defense, and symlink-boundary defense.
- Coding Worker diff, artifact, command-log, review, rework, and idempotency.
- Sandbox policy, MockSandboxRunner, DockerSandboxRunner, and optional
  CodexWorker sandbox hook behavior.
- Manual real Codex CLI smoke, small code-task, and multi-file merge candidate
  tests, skipped by default.

## Local Commands

```powershell
.\.venv\Scripts\python -m ruff format .
.\.venv\Scripts\python -m ruff check .
.\.venv\Scripts\python -m mypy src tests
.\.venv\Scripts\python -m pytest -q
```

The implementation host currently uses Python 3.13 for local feedback. The
project baseline gate remains Python 3.12 in GitHub Actions.

## Manual Real Codex Smoke Test

The real Codex CLI smoke test is not part of default pytest or CI execution. It
requires a local Codex CLI session and explicit opt-in:

```powershell
$env:AI_ORG_ENABLE_REAL_CODEX_SMOKE = "true"
.\.venv\Scripts\python -m pytest tests\manual\test_real_codex_smoke.py -q
```

The test creates a temporary Git repository, runs a `codex_mode="local_cli"`
TaskSpec through the normal WorkerRegistry and workflow, creates a task
worktree, asks Codex to create only `smoke/codex_worker_smoke.txt`, records
logical artifact URIs, and asserts that the main branch remains unchanged.

Default pytest collection excludes `tests/manual` through `pyproject.toml`.
When the file is run explicitly and `AI_ORG_ENABLE_REAL_CODEX_SMOKE` is unset,
the test is skipped. CI sets the opt-in variable to `false` and does not require
Codex credentials.

## Manual Real Codex Small Code Task

The small code-task test is not part of default pytest or CI execution. It
requires a local Codex CLI session, Docker, and explicit opt-in:

```powershell
$env:AI_ORG_ENABLE_REAL_CODEX_CODE_TASK = "true"
.\.venv\Scripts\python -m pytest tests\manual\test_real_codex_code_task.py -q
```

The test runs a `codex_mode="local_code_task"` TaskSpec through the normal
WorkerRegistry and workflow, creates a task worktree, asks Codex to create only
the fixed smoke helper and unit-test files, runs a fixed DockerSandboxRunner
validation command, records logical artifact URIs, and asserts that the main
branch remains unchanged. If Docker is unavailable, the manual test skips with a
clear reason and the stage report must not claim local Docker execution passed.

## Manual Real Codex Multi-File Merge Candidate Task

The multi-file task test is not part of default pytest or CI execution. It
requires a local Codex CLI session, Docker, and explicit opt-in:

```powershell
$env:AI_ORG_ENABLE_REAL_CODEX_MULTI_FILE_TASK = "true"
.\.venv\Scripts\python -m pytest tests\manual\test_real_codex_multi_file_task.py -q
```

The test runs a `codex_mode="local_multi_file_task"` TaskSpec through the normal
WorkerRegistry and workflow, creates a task worktree, asks Codex to modify only
`docs/MERGE_APPROVAL.md`,
`src/ai_org/adapters/codex/merge_candidate.py`, and
`tests/unit/test_codex_merge_candidate.py`, runs a fixed DockerSandboxRunner
validation command, records logical artifact URIs, creates a
`merge_candidate.created` audit event after independent Review Worker
acceptance, and asserts that the main branch remains unchanged. If Docker is
unavailable, the manual test skips with a clear reason and the stage report must
not claim local Docker execution passed.

## PostgreSQL Integration

Tests marked `postgres` run in two modes:

- GitHub Actions service mode with `AI_ORG_USE_EXISTING_POSTGRES=true`,
  `AI_ORG_DATABASE_URL`, and `AI_ORG_CHECKPOINT_DATABASE_URL`.
- Local Docker Compose mode when Docker is available.

If Docker is unavailable locally, PostgreSQL tests skip with a clear reason.
CI uses `postgres:16.6`.

## Docker Sandbox Integration

Docker sandbox integration tests run fixed safe commands and do not execute
user-provided code:

```powershell
.\.venv\Scripts\python -m pytest tests\integration\test_docker_sandbox.py -q
```

If Docker is unavailable locally, these tests skip with an explicit message. In
GitHub Actions, Docker unavailability fails the Docker sandbox integration step.

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
  tests/unit/test_codex_diff.py \
  tests/unit/test_codex_merge_candidate.py \
  tests/unit/test_codex_worker.py \
  tests/unit/test_ci_real_codex_disabled.py \
  tests/unit/test_merge_candidate_audit.py \
  tests/integration/test_codex_worker_workflow.py \
  tests/e2e/test_api.py \
  -q
python -m pytest tests/integration/test_docker_sandbox.py -q
python -m pytest -q
```

The workflow also verifies `requirements-lock.txt`, runs `pip-audit`, generates
a license report and CycloneDX SBOM, runs `detect-secrets`, and runs
`git diff --check`.

## External Services

Tests do not call real LLMs, real Codex, OpenHands, paid services, or
user-provided untrusted code. Codex Worker tests use only `MockCodexClient`,
`DryRunCodexClient`, and NOT_CONFIGURED `LocalCodexCliClient` behavior unless
the manual smoke, small code-task, or multi-file merge candidate tests are
explicitly opted in locally.
