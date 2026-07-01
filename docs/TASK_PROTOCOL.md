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

Workers must return an `AgentResult`. A free-text-only worker response is not
accepted as the protocol shape.

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

The current Mock Workers return deterministic results and never call external
services.

## ReviewReport

`ReviewReport` contains:

- `task_id`
- `decision`
- `criteria_results`
- `defects`
- `rework_instructions`
- `confidence`

The review worker is separate from production workers. It can accept, reject, or
request rework. The test scenario uses `force_rework` as a deterministic
acceptance criterion to exercise bounded retry behavior.

## Codex Stub

`CodexDryRunWorker` implements the same worker interface but returns a dry-run
result. It does not start Codex, require an API key, run shell commands, or modify
external repositories.
