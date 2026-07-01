# Controlled Real Codex Smoke Test

## Purpose

The controlled real Codex smoke test verifies that a `codex` Worker can call the
local Codex CLI through the normal first-layer workflow without modifying the
main branch or bypassing review.

This is not a production execution sandbox and not a general code-writing
capability.

## Preconditions

- `codex --version` succeeds.
- `codex doctor --json` confirms local readiness. The worker does not persist
  auth details.
- The process has explicit opt-in:

```powershell
$env:AI_ORG_ENABLE_REAL_CODEX_SMOKE = "true"
```

Without this variable, `LocalCodexCliClient` returns `NOT_CONFIGURED` and does
not start Codex.

## Execution Path

The smoke test uses:

```text
codex --sandbox workspace-write --ask-for-approval on-request exec --json --cd <worktree> --color never -
```

The prompt is sent through stdin. The CLI runs with `cwd` set to the task
worktree and with `--cd <worktree>`.

## Task Scope

Allowed files:

- `smoke/**`

Expected change:

- `smoke/codex_worker_smoke.txt`

Forbidden files include `.git/**`, `.github/**`, `.env*`, `requirements*.txt`,
`pyproject.toml`, `alembic/**`, `src/**`, `tests/**`, `docs/**`, `AGENTS.md`,
and `README.md`.

## Review And Artifacts

`DiffCollector` records changed files and diff summaries. `CommandLogCollector`
records summarized command logs. Prompt, diff, and command logs are sanitized.
Worktree paths are exposed as logical `worktree://...` URIs, and raw local
worktree paths in Codex JSONL summaries are replaced with `<worktree>`.

The independent Review Worker accepts the task only when the smoke file is the
only changed file and no policy violations are detected.

## Manual Command

```powershell
$env:AI_ORG_ENABLE_REAL_CODEX_SMOKE = "true"
.\.venv\Scripts\python -m pytest tests\manual\test_real_codex_smoke.py -q
```

This test is skipped by default and is not part of CI credentials or CI success.

## Failure Statuses

- `NOT_CONFIGURED`: missing opt-in, missing CLI, or authentication not ready.
- `FAILED`: unsafe local_cli configuration, timeout, or CLI execution failure.
- `SUCCEEDED`: CLI exited 0, diff is scoped, and independent review accepted.

## Not Implemented

- Codex MCP integration.
- Docker sandbox for untrusted code.
- Automatic commit, merge, or push of Codex output.
- Production-grade permission and budget enforcement.
