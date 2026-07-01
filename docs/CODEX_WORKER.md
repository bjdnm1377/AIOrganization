# Codex Worker

## Implemented

`CodexWorker` is registered under `worker_type="codex"` through the existing
WorkerRegistry. It accepts a normal `WorkerRequest`, creates a task-scoped Git
worktree, renders a constrained coding prompt, delegates to a `CodexClient`, and
returns a structured `AgentResult`.

Implemented clients:

- `MockCodexClient`: deterministic local file change simulation for tests.
- `DryRunCodexClient`: no-op dry run that records no real Codex process.
- `LocalCodexCliClient`: explicit NOT_CONFIGURED stub. It does not invoke real
  Codex in this stage.

No default code path requires an OpenAI key, Codex login, paid service, or real
shell execution.

## AgentResult Metadata

Codex Worker metadata includes:

- `codex_mode`
- `worktree_path`
- `branch_name`
- `base_commit`
- `head_commit`
- `changed_files`
- `diff_summary`
- `tests_run`
- `command_logs`
- `codex_thread_id`
- `session_id`
- `blocked_reason`
- `policy_violations`

Large diff and log content is written as artifact files under
`.ai_org_artifacts/`; prompt, diff, and command-log artifacts are sanitized
before writing. API responses expose only logical artifact metadata, not local
file paths or artifact contents.

## Not Implemented

- Real Codex CLI or MCP execution.
- Automatic merge to the main branch.
- Docker code-execution sandbox.
- OpenHands or other external agent runtime.
