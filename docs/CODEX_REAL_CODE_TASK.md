# Real Codex Small Code Task

## Status

Implemented as a manual, explicitly opted-in validation path. It is not part of
default pytest or GitHub Actions.

## Purpose

This path verifies that a real local Codex CLI task can travel through the
first-layer system without bypassing core boundaries:

- TaskSpec and WorkerRegistry dispatch;
- task-scoped Git worktree creation;
- `LocalCodexCliClient` execution with explicit opt-in;
- fixed DockerSandboxRunner validation command;
- DiffCollector and CommandLogCollector artifact creation;
- independent Review Worker acceptance;
- audit event persistence;
- no main-branch modification;
- no automatic commit, merge, or push.

## Required Opt-In

Real execution is disabled unless all of these are true:

- environment variable `AI_ORG_ENABLE_REAL_CODEX_CODE_TASK=true`;
- task metadata `codex_mode="local_code_task"`;
- local `codex --version` succeeds;
- `codex doctor --json` confirms local readiness;
- Docker is available for the manual test.

If opt-in is absent, the client returns NOT_CONFIGURED and no Codex process is
started. CI sets `AI_ORG_ENABLE_REAL_CODEX_CODE_TASK=false`.

## Allowed Files

The current small code task is intentionally narrow. Policy fixes the writable
scope to:

- `src/ai_org/adapters/codex/smoke_helpers.py`
- `tests/unit/test_codex_smoke_helpers.py`

Task metadata cannot widen this file set.

## Forbidden Files

The real code-task policy forbids:

- `.git/**`
- `.github/**`
- `.env`
- `.env.*`
- `requirements-lock.txt`
- `requirements.in`
- `pyproject.toml`
- `alembic/**`
- `docs/**`
- `AGENTS.md`
- `README.md`
- `docker-compose.yml`
- `scripts/**`

Any forbidden changed file is captured by `DiffCollector` and rejected by the
independent Review Worker.

## Codex Invocation

`LocalCodexCliClient` invokes Codex as:

```text
codex --sandbox workspace-write --ask-for-approval on-request exec --json --cd <worktree> --color never -
```

The prompt is sent through stdin. Command logs redact local paths and summarize
Codex JSONL without storing raw auth details, tokens, environment variables, or
absolute worktree paths.

## Sandbox Validation

When `sandbox_test_profile="real_code_task_smoke"` is present, `CodexWorker`
runs a fixed Python assertion command through the configured `SandboxRunner`.
The command imports the generated helper, checks deterministic formatting, and
verifies the expected test file exists.

The Docker path uses the existing sandbox controls: non-root user,
`--network none`, `--cap-drop ALL`, `no-new-privileges`, read-only rootfs,
tmpfs `/tmp`, task-worktree mount only, and resource/output limits.
`PYTHONDONTWRITEBYTECODE=1` is set to avoid test artifacts in the worktree.

## Manual Test Command

```powershell
$env:AI_ORG_ENABLE_REAL_CODEX_CODE_TASK = "true"
.\.venv\Scripts\python -m pytest tests\manual\test_real_codex_code_task.py -q
```

The manual test skips when the environment variable is absent, Codex CLI is not
installed, or Docker is unavailable. A skip is not reported as a successful real
code task.

## Not Implemented

- CI execution of real Codex.
- OpenAI API key handling.
- Automatic commit, merge, or push of Codex output.
- Multi-file merge approval is handled by the separate
  `AI_ORG_ENABLE_REAL_CODEX_MULTI_FILE_TASK=true` manual path and still stops
  at a pending MergeCandidate summary.
- Production arbitrary-code sandboxing.
- User-provided shell command execution in Docker.
- OpenHands, Virtuoso, HFSS, MATLAB, Redis, Temporal, or Web frontend
  integration.
