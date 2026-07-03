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
- Local Codex CLI stepwise multi-file task opt-in, missing CLI, restricted
  command construction, fixed logical file scope, per-step single-file scope,
  per-step timeout classification, per-step main-worktree fingerprint checks,
  MergeCandidate artifact creation, and Docker sandbox test-log behavior.
- Codex CLI exec timeout classification as `CODEX_CLI_TIMEOUT`, timeout
  command-log diagnostics, process-tree cleanup metadata, deterministic
  validation blocking, Review Worker rejection, and no accepted MergeCandidate
  artifact after timeout.
- Codex step timeout classification as `CODEX_STEP_TIMEOUT`, failed step index
  recording, process-tree cleanup metadata, Review Worker rejection, and no
  accepted MergeCandidate artifact after timeout.
- Codex CLI diagnostic opt-in, safe command construction, stdin versus
  argument prompt shape, JSONL auth/path redaction, timeout classification,
  process-tree cleanup metadata, main-worktree post-check reporting, Review
  Worker timeout rejection, and no MergeCandidate/auto-merge/auto-push
  diagnostic artifact state.
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
- Manual real Codex CLI smoke, small code-task, single-call multi-file, and
  stepwise multi-file merge candidate tests, skipped by default.

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
`src/ai_org/adapters/codex/merge_candidate.py`, and
`tests/unit/test_codex_merge_candidate.py`, runs a fixed DockerSandboxRunner
validation command, records logical artifact URIs, creates a
`merge_candidate.created` audit event after independent Review Worker
acceptance, and asserts that the main branch remains unchanged. If Docker is
unavailable, the manual test skips with a clear reason and the stage report must
not claim local Docker execution passed.

The current real multi-file prompt is intentionally shorter than the earlier
three-file version. Documentation updates are not included in the real Codex
task; this reduces timeout risk without increasing permissions or relaxing file
policy.

The latest single-call real multi-file run still timed out before producing a
diff. That result remains blocked and is not reported as a passing
MergeCandidate.

## Manual Real Codex Stepwise Multi-File Merge Candidate Task

The stepwise multi-file task test is not part of default pytest or CI
execution. It requires a local Codex CLI session, Docker, and explicit opt-in:

```powershell
$env:AI_ORG_ENABLE_REAL_CODEX_STEPWISE_MULTI_FILE_TASK = "true"
.\.venv\Scripts\python -m pytest tests\manual\test_real_codex_stepwise_multi_file_task.py -q
```

The test runs `codex_mode="local_stepwise_multi_file_task"` through the normal
WorkerRegistry and workflow. `CodexWorker` splits the logical task into two
real Codex CLI invocations: one source-file step and one test-file step. Each
step uses the task worktree as cwd/`--cd`, one allowed file, independent
forbidden files, timeout diagnostics, and a main-worktree fingerprint gate. If
both steps succeed, `DockerSandboxRunner` runs
`python -m pytest tests/unit/test_codex_merge_candidate.py -q`, the independent
Review Worker must accept, and the application records a pending
MergeCandidate audit event. The test asserts no automatic merge or push and no
main-branch modification.

## Manual Real Codex CLI Diagnostics

The CLI diagnostic test is not part of default pytest or CI execution. It is
the current recovery path after the single-call and stepwise real multi-file
tasks timed out. It requires a local Codex CLI session and explicit opt-in:

```powershell
$env:AI_ORG_ENABLE_REAL_CODEX_DIAGNOSTICS = "true"
.\.venv\Scripts\python -m pytest tests\manual\test_real_codex_cli_diagnostics.py -q
```

The test creates an independent temporary Git repository, runs `codex
--version`, `codex doctor --json`, a read-only `codex exec` prompt, a stdin
versus command-argument prompt comparison, and a single-file create diagnostic
limited to `diagnostic/codex_diag.txt`. It writes a sanitized JSON diagnostic
artifact under `.ai_org_artifacts/codex-cli-diagnostics/`, records the project
main-worktree fingerprint before and after the run, and asserts no project
source change. It does not run Docker, create a MergeCandidate, merge, push,
commit, or enter MergeService work.

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

`.github/workflows/verification.yml` uses Python 3.12, sets all real Codex
opt-ins to `false` including
`AI_ORG_ENABLE_REAL_CODEX_STEPWISE_MULTI_FILE_TASK` and
`AI_ORG_ENABLE_REAL_CODEX_DIAGNOSTICS`, and runs:

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
`DryRunCodexClient`, and NOT_CONFIGURED or fake-runner `LocalCodexCliClient`
behavior unless the manual smoke, small code-task, single-call multi-file, or
stepwise multi-file merge candidate tests, or the standalone CLI diagnostics,
are explicitly opted in locally.
