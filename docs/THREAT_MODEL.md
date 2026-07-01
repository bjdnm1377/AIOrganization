# Threat Model

## Assets

- Project, task, approval, worker-run, and audit records.
- LangGraph checkpoint state.
- Worker outputs and artifacts metadata.
- Dependency lock file and migration files.

## Trust Boundaries

- FastAPI input boundary.
- Application service and domain state transition boundary.
- Worker adapter boundary.
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
- No real shell, real Codex, real LLM, or untrusted-code execution.

## Known Risks

- Live PostgreSQL checkpoint recovery was not executed on this host because
  Docker is unavailable.
- Role-level PostgreSQL grants are documented but not provisioned locally.
- Checkpoint cleanup is documented but not implemented.
- Mock Workers do not represent real external-runtime failure modes.

## Future Controls

- Separate database roles for application, checkpoint, and migration.
- Artifact storage policy and retention.
- Runtime sandbox for Coding Worker in a later stage.
- Policy engine for permissions and budget.
- CI supply-chain gates for vulnerability, license, SBOM, and secret scanning.
