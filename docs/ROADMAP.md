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
- Real Codex CLI diagnostics with bounded version, doctor, read-only exec, and
  single-file create scenarios in an independent temporary repository. The
  latest single-file create diagnostic timed out on this host and remains
  blocked; it is not a passing real Codex result.
- Human-approved controlled merge foundation that uses Mock, DryRun, or manual
  fixture MergeCandidates, requires explicit approval, checks base commit and
  forbidden files, blocks secret/path-bearing patches, applies patches only in
  a temporary integration clone, runs configured tests, writes audit events,
  and does not push or deploy.

## Current Stage

- Human-approved controlled merge workflow validation without real Codex CLI.
  The current stage verifies MergeCandidate structure, MergeApprovalService,
  controlled MergeService, API endpoints, audit events, security gates, local
  tests, supply-chain checks, and CI while all real Codex opt-ins remain
  disabled by default.

## Next Stage

After this foundation is accepted, the next stage should return to real Codex
runtime repair or alternate execution-environment evaluation:

- Re-run diagnostics from WSL/Linux, a different Codex CLI version, Codex App
  worktree, or remote host.
- Keep finite timeouts and fingerprint gates.
- Do not use `danger-full-access`.
- Do not treat Codex timeouts as passing MergeCandidates.

Only after real Codex diagnostics and a later controlled real Coding Worker task
pass without timeout or isolation violations should a production branch-merge
implementation be expanded beyond the current fixture/integration-clone
foundation:

- Keep Codex behind Worker and CodexClient ports.
- Preserve task-scoped Git worktrees and Review Worker gating.
- Route formatter/test/build commands through the sandbox runner by default.
- Keep approval gates for shell, network, and file-system permission increases.
- Continue to avoid untrusted user code and automatic merge until a later stage.
- Extend MergeService persistence and branch operation design with fresh
  re-checks of candidate, branch, tests, policy, and explicit human approval.
- Keep automatic push and deploy out of scope unless separately approved.

## Later Stages

- Production hardening for arbitrary Coding Worker execution.
- Checkpoint and worktree cleanup jobs.
- Permission and budget domain model.
- Artifact store and retention policy.
- Optional OpenHands or other execution runtime only after a new ADR.
