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

Codex Worker metadata includes `codex_mode`, `worktree_path`, `branch_name`,
`base_commit`, `head_commit`, `changed_files`, `diff_summary`, `tests_run`,
`command_logs`, optional session identifiers, `blocked_reason`, and
`policy_violations`.

## ReviewReport

The Review Worker is separate from production workers. It can accept, reject, or
request rework. Coding Worker results with forbidden file changes, disallowed
commands, suspicious diff markers, or NOT_CONFIGURED runtime status are not
accepted. Failed coding tests trigger bounded rework.

## Real Codex Status

`MockCodexClient` and `DryRunCodexClient` are implemented and used by default.
`LocalCodexCliClient` is a NOT_CONFIGURED stub and does not invoke real Codex in
this stage.
