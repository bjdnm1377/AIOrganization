# Codex Worker

## Implemented

`CodexWorker` is registered under `worker_type="codex"` through the existing
WorkerRegistry. It accepts a normal `WorkerRequest`, creates a task-scoped Git
worktree, renders a constrained coding prompt, delegates to a `CodexClient`, and
returns a structured `AgentResult`.

Implemented clients:

- `MockCodexClient`: deterministic local file change simulation for tests.
- `DryRunCodexClient`: no-op dry run that records no real Codex process.
- `LocalCodexCliClient`: optional local real Codex CLI smoke path. It returns
  NOT_CONFIGURED unless `AI_ORG_ENABLE_REAL_CODEX_SMOKE=true` is set.

No default code path requires an OpenAI key, Codex login, paid service, or real
shell execution. CI uses only Mock/DryRun and NOT_CONFIGURED behavior.

## Local Real Codex CLI Smoke Path

The real path is deliberately narrow:

- `LocalCodexCliClient` first checks explicit opt-in.
- It detects the installed CLI with `codex --version`.
- It runs `codex doctor --json` as a fail-closed preflight and records only
  coarse readiness, not auth details; raw doctor output is not persisted.
- It rejects `danger-full-access` and other unapproved sandbox values.
- It rejects approval policies other than `on-request` or `untrusted`.
- It invokes Codex as:
  `codex --sandbox workspace-write --ask-for-approval on-request exec --json --cd <worktree> --color never -`.
- It passes the rendered prompt through stdin, not command-line arguments.
- It masks the task worktree path in command-log summaries as `<worktree>`.
- It never commits, merges, pushes, or applies changes to the main branch.

The smoke task is expected to create only `smoke/codex_worker_smoke.txt` in the
task worktree. The independent Review Worker accepts the result only if
`DiffCollector` reports no forbidden files, no disallowed commands, and no
suspicious secret markers. Task metadata cannot widen the real CLI file scope
beyond `smoke/**`.

## AgentResult Metadata

Codex Worker metadata includes:

- `codex_mode`
- `worktree_path`
- `worktree_uri`
- `branch_name`
- `base_commit`
- `head_commit`
- `changed_files`
- `diff_summary`
- `tests_run`
- `command_logs`
- `blocked_reason`
- `policy_violations`
- `codex_preflight_passed`
- `codex_thread_observed`
- `codex_session_observed`
- `external_service_requested`

Large diff and log content is written as artifact files under
`.ai_org_artifacts/`; prompt, diff, and command-log artifacts are sanitized
before writing. API responses expose logical artifact metadata and logical
worktree URIs, not local file paths or artifact contents.

## Not Implemented

- Codex MCP execution.
- Automatic merge to the main branch.
- Docker code-execution sandbox.
- OpenHands or other external agent runtime.
