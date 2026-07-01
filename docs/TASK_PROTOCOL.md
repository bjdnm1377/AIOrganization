# Task Protocol

## Pydantic Contracts

The shared protocol models are defined in `src/ai_org/protocols/schemas.py`.

- `CreateProjectRequest`
- `ProjectResponse`
- `TaskSpec`
- `AgentResult`
- `ReviewReport`
- `ApprovalRequest`
- `ApprovalDecision`
- `WorkflowStatus`

Workers must return an `AgentResult`; free-text-only worker responses are not an
accepted protocol shape.

## TaskSpec Metadata

`TaskSpec.metadata` is persisted on `Task.metadata` and is used for constrained
execution settings. For Codex tasks, supported keys include:

- `codex_mode`: `dry_run`, `mock`, or `local_cli`.
- `allowed_files` and `forbidden_files`.
- `allowed_commands` and `forbidden_commands`.
- `required_tests`.
- `codex_sandbox`: for `local_cli`, allowed values are `workspace-write` and
  `read-only`; default is `workspace-write`.
- `codex_approval_policy`: for `local_cli`, allowed values are `on-request` and
  `untrusted`; default is `on-request`.
- `mock_output_file`.
- `simulate_forbidden_file`, `simulate_test_failure`,
  `simulate_not_configured`, and `simulate_secret_output` for deterministic
  tests.

## AgentResult

`AgentResult` contains:

- `task_id`
- `status`
- `summary`
- `artifacts`
- `evidence`
- `tests_run`
- `assumptions`
- `risks`
- `unresolved_questions`
- `metadata`

Codex Worker metadata includes `codex_mode`, logical `worktree_path` /
`worktree_uri`, `branch_name`, `base_commit`, `head_commit`, `changed_files`,
`diff_summary`, `tests_run`, summarized `command_logs`, optional
`codex_thread_observed` / `codex_session_observed` booleans, `blocked_reason`,
and `policy_violations`.

## ReviewReport

The Review Worker is separate from production workers. It can accept, reject, or
request rework. Coding Worker results with forbidden file changes, disallowed
commands, suspicious diff markers, or NOT_CONFIGURED runtime status are not
accepted. Failed coding tests trigger bounded rework.

## Real Codex Status

`MockCodexClient` and `DryRunCodexClient` are implemented and used by default.
`LocalCodexCliClient` is implemented as a manual real Codex CLI smoke path. It
returns `NOT_CONFIGURED` unless `AI_ORG_ENABLE_REAL_CODEX_SMOKE=true` is set and
the local Codex CLI is installed and authenticated. CI never enables this flag.

The real smoke path can return:

- `NOT_CONFIGURED`: no opt-in, missing CLI, or auth not ready.
- `FAILED`: timeout, unsafe configuration, or CLI execution failure.
- `SUCCEEDED`: Codex CLI completed and independent review accepted the scoped
  smoke diff.
