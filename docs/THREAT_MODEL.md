# Threat Model

## Assets

- Project, task, approval, worker-run, and audit records.
- LangGraph checkpoint state.
- Worker outputs and artifact metadata.
- Codex task worktrees, diff artifacts, prompt artifacts, and command-log
  artifacts.
- Dependency lock file and migration files.

## Trust Boundaries

- FastAPI input boundary.
- Application service and domain state transition boundary.
- WorkerRegistry and Worker adapter boundary.
- CodexClient and worktree boundary.
- PostgreSQL business schema boundary.
- LangGraph checkpoint schema boundary.

## Current Controls

- Structured Pydantic request and response models.
- Domain transition guards.
- Optimistic version fields on mutable entities.
- Idempotency keys for WorkerRun and Approval records.
- Independent Review Worker.
- Strict msgpack checkpoint serializer with pickle fallback disabled.
- API exception handler returns sanitized errors.
- Codex Worker creates task-scoped Git worktrees and does not merge to the main
  branch.
- Coding policy detects forbidden file changes, disallowed commands, suspicious
  diff markers, and failed tests before review acceptance.
- System baseline forbidden files cannot be removed by task metadata.
- Prompt, diff, and command logs are sanitized before artifact persistence.
- Default tests do not call real shell, real Codex, real LLM, or untrusted code.

## Known Risks

- Real Codex runtime is not implemented.
- Production sandboxing is not implemented.
- Worktree cleanup is manual in this stage.
- Role-level PostgreSQL grants are documented but not provisioned locally.
- Checkpoint cleanup is documented but not implemented.
- Mock clients do not represent every real external-runtime failure mode.

## Future Controls

- Controlled real Codex smoke test after explicit user approval.
- Docker or equivalent execution sandbox design before untrusted code execution.
- Stronger permission and budget domain model.
- Separate database roles for application, checkpoint, and migration.
- Artifact retention and cleanup policy.
