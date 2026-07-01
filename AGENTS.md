# AI Organization Agent Guide

This repository implements a two-layer AI organization system. The current
stage includes the minimal persistent workflow plus Mock/DryRun Codex Coding
Worker isolation.

## Current Boundaries

- Do not call real LLMs.
- Do not request or use real API keys.
- Do not start real Codex tasks by default. The only current exception is the
  controlled local smoke test with explicit `AI_ORG_ENABLE_REAL_CODEX_SMOKE=true`
  opt-in.
- Do not integrate OpenHands, Virtuoso, HFSS, MATLAB, Redis, or Temporal.
- Do not execute user-provided untrusted code.
- Do not implement a real Docker code-execution sandbox in this stage.
- All default tests must run without API keys or paid services.

## Architecture Boundaries

- `domain` must not import LangGraph, FastAPI, SQLAlchemy, or Alembic types.
- `application` owns use cases and transaction-oriented coordination.
- `orchestration` owns LangGraph adapter code and workflow nodes.
- `ports` defines Worker, Repository, and CodexClient interfaces.
- `adapters` contains concrete implementations such as in-memory storage,
  PostgreSQL mapping, FastAPI, Mock Workers, and Codex Mock/DryRun adapters.
- Codex Worker changes must stay inside task-scoped Git worktrees and must not
  merge into the main branch automatically.
- Real Codex smoke changes must stay limited to `smoke/**` and must be reviewed
  independently before acceptance.
- Workers must return structured results, not free text as the only output.
- Review Workers must stay independent from the worker that produced the result.

## Checkpoint Safety

- Configure strict msgpack before importing LangGraph modules.
- Do not enable pickle fallback.
- Use an explicit serializer allowlist.
- Store only controlled primitive values, TypedDict-compatible data, or explicit
  Pydantic model payloads in checkpoint state.
- Do not store database connections, file handles, locks, model clients, or
  executable objects in checkpoint state.

## Development Workflow

- Keep implementation steps small and test-backed.
- Lock every direct dependency version and record its purpose.
- Documentation must describe the real implementation, not planned capability.
- Before committing, run formatting, lint, type checks, tests, secret scanning,
  and available supply-chain checks.
