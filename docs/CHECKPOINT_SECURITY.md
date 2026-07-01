# Checkpoint Security

## Implemented Controls

- `LANGGRAPH_STRICT_MSGPACK=true` is set before LangGraph imports in workflow
  modules.
- Serializer construction disables pickle fallback.
- Serializer construction passes an explicit allowed msgpack module list.
- Startup self-check verifies strict msgpack mode and rejects unsafe serializer
  configuration.
- Workflow state is kept to primitive JSON-like values and validated before graph
  invocation.
- Tests cover strict-mode self-check, illegal checkpoint state rejection, and
  rejection of pickle/unknown deserialization payloads.

Implementation: `src/ai_org/orchestration/checkpoint_security.py`

## Allowed Checkpoint State

The current `WorkflowState` includes only:

- `project_id`
- `selected_task_id`
- `needs_approval`
- `approval_id`
- `approval_decision`
- serialized `AgentResult`
- serialized `ReviewReport`
- `review_outcome`

Database connections, file handles, locks, model clients, subprocess handles,
and executable objects are explicitly not allowed in state.

## Data Classification

Checkpoint state is operational recovery data. It may include task identifiers,
review summaries, and deterministic worker metadata. It must not include raw
secrets, database passwords, environment dumps, API keys, or unrestricted tool
outputs.

## PostgreSQL Permissions

Recommended production split:

- application role: read/write business tables in `ai_org`.
- checkpoint role: read/write checkpoint tables in `langgraph_checkpoint`.
- migration role: create/alter schemas during migrations only.

`postgres_checkpointer(..., setup=False)` is the runtime default and does not run
checkpoint DDL. `setup=True` is reserved for initialization/tests. Role
provisioning is environment-specific and not executed on the local host.

## Retention And Cleanup

Checkpoint rows should be retained while a project may resume. After terminal
states (`COMPLETED`, `BLOCKED`, `FAILED`) and a configured retention window,
checkpoint rows can be deleted. The cleanup command is not implemented yet.
