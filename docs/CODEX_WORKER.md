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
  NOT_CONFIGURED unless the matching explicit opt-in is set.

No default code path requires an OpenAI key, Codex login, paid service, or real
shell execution. CI uses only Mock/DryRun and NOT_CONFIGURED behavior.

## Optional Sandbox Hook

`CodexWorker` can receive a `SandboxRunner` implementation. It only invokes the
sandbox when task metadata requests a fixed profile:

- `sandbox_smoke=True` runs a fixed health check and records `sandbox.health`.
- `sandbox_test_profile="real_code_task_smoke"` runs a fixed Python validation
  command after a small real code task and records `sandbox.test`.

These hooks verify integration with the sandbox foundation without executing
user-provided commands or calling real Codex inside Docker.

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

## Local Real Codex Small Code Task Path

The small code-task path uses the same `LocalCodexCliClient` but requires the
separate opt-in `AI_ORG_ENABLE_REAL_CODEX_CODE_TASK=true` and task metadata
`codex_mode="local_code_task"`.

Current allowed files are fixed in policy:

- `src/ai_org/adapters/codex/smoke_helpers.py`
- `tests/unit/test_codex_smoke_helpers.py`

Task metadata cannot widen this scope. The code task still uses
`workspace-write`, `on-request`, stdin prompt delivery, a task worktree,
sanitized command logs, `DiffCollector`, logical artifact URIs, and independent
Review Worker acceptance. It does not commit, merge, push, or change the main
working tree.

When `sandbox_test_profile="real_code_task_smoke"` is present,
`DockerSandboxRunner` runs a fixed import/assert command inside the worktree. If
no sandbox runner is configured, the result records
`SANDBOX_RUNNER_NOT_CONFIGURED` and review requires rework instead of accepting
the task.

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
- Running real Codex or arbitrary user commands inside Docker.
- Automatic commit of Codex output branches.
- OpenHands or other external agent runtime.
