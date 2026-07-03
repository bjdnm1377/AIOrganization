# Roadmap

## Completed

- Minimal domain model and state machine.
- Pydantic v2 protocol models.
- Worker port, WorkerRegistry, Mock Workers, and independent Review Worker.
- LangGraph workflow with low-risk execution and high-risk approval interrupt.
- In-memory persistence for default local API and tests.
- PostgreSQL SQLAlchemy models and Alembic migrations.
- Strict checkpoint serializer self-check.
- FastAPI control/query endpoints.
- GitHub Actions Python 3.12 and PostgreSQL verification.
- Codex Mock/DryRun Worker with task worktree isolation, diff/log artifacts,
  policy checks, independent review gating, API artifact metadata queries, and
  tests.
- Controlled local real Codex CLI smoke path with explicit opt-in, task
  worktree, smoke-only file policy, command-log sanitization, independent
  review, and manual test coverage.
- Docker sandbox foundation with SandboxRunner port, Mock and Docker adapters,
  default disabled network, mount/resource policy checks, fixed safe Docker
  integration tests, and optional CodexWorker sandbox smoke hook.
- Controlled real Codex small code-task path with separate opt-in, fixed
  allowed files, task worktree isolation, fixed DockerSandboxRunner validation,
  sanitized artifacts, independent review, no automatic merge, manual local
  validation, and GitHub Actions verification with real Codex disabled.
- Controlled real Codex multi-file merge candidate path with separate opt-in,
  fixed allowed files, task worktree isolation, fixed DockerSandboxRunner
  validation, sanitized artifacts, independent review, `merge_candidate.created`
  audit event, no automatic commit, merge, push, PR, or deploy, and a
  fail-closed main-worktree fingerprint guard. The prior real validation found
  a main-worktree modification. A later revalidation kept the main-worktree
  fingerprint stable but timed out during Codex CLI exec, so the current stage
  is timeout reduction and revalidation before any merge implementation.
- Controlled real Codex stepwise multi-file orchestration implementation with
  fixed single-file steps, independent allowed/forbidden files, per-step
  timeout diagnostics, main-worktree fingerprint checks, task-worktree
  dirty-file checks, fixed sandbox validation, independent review, and pending
  MergeCandidate artifact generation only. Real manual validation still timed
  out in the first step, so it is not accepted as a passing real Codex result.

## Current Stage

- Real Codex CLI single-file diagnostics. The system now diagnoses whether the
  local Codex CLI can complete version, doctor, read-only exec, stdin versus
  argument prompt shape, and one minimal single-file create scenario in an
  independent temporary Git repository. The diagnostics preserve finite
  timeouts, JSONL/process-cleanup evidence, main-worktree fingerprint
  post-checks, no MergeCandidate, no merge, and no push. This stage must pass
  locally and CI must keep real Codex disabled before any further real Coding
  Worker task is attempted.

## Next Stage

Only after the CLI diagnostics and a later controlled real Coding Worker task
pass without timeout or isolation violations, the next stage may be
human-approved merge implementation:

- Keep Codex behind Worker and CodexClient ports.
- Preserve task-scoped Git worktrees and Review Worker gating.
- Route formatter/test/build commands through the sandbox runner by default.
- Keep approval gates for shell, network, and file-system permission increases.
- Continue to avoid untrusted user code and automatic merge until a later stage.
- Implement a MergeService that re-checks the MergeCandidate, branch, tests,
  policy, and explicit human approval before any branch merge.
- Keep automatic push and deploy out of scope unless separately approved.

## Later Stages

- Production hardening for arbitrary Coding Worker execution.
- Checkpoint and worktree cleanup jobs.
- Permission and budget domain model.
- Artifact store and retention policy.
- Optional OpenHands or other execution runtime only after a new ADR.
