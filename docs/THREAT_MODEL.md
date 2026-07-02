# Threat Model

## Assets

- Project, task, approval, worker-run, and audit records.
- LangGraph checkpoint state.
- Worker outputs and artifact metadata.
- Codex task worktrees, diff artifacts, prompt artifacts, and command-log
  artifacts.
- MergeCandidate artifacts and audit events awaiting human approval.
- Docker sandbox command logs and task worktree mounts.
- Dependency lock file and migration files.

## Trust Boundaries

- FastAPI input boundary.
- Application service and domain state transition boundary.
- WorkerRegistry and Worker adapter boundary.
- CodexClient and worktree boundary.
- SandboxRunner and container boundary.
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
- Local real Codex CLI smoke execution requires explicit
  `AI_ORG_ENABLE_REAL_CODEX_SMOKE=true` opt-in.
- Local real Codex CLI small code-task execution requires separate explicit
  `AI_ORG_ENABLE_REAL_CODEX_CODE_TASK=true` opt-in.
- Local real Codex CLI multi-file execution requires separate explicit
  `AI_ORG_ENABLE_REAL_CODEX_MULTI_FILE_TASK=true` opt-in.
- Local real Codex CLI smoke execution uses `workspace-write` sandbox,
  `on-request` approval, and `--cd <worktree>`.
- Coding policy detects forbidden file changes, disallowed commands, suspicious
  diff markers, and failed tests before review acceptance.
- System baseline forbidden files cannot be removed by task metadata.
- `local_cli` smoke policy narrows default writes to `smoke/**` and forbids
  source, tests, docs, workflow, dependency, migration, and repository-control
  files.
- `local_code_task` policy narrows writes to the fixed smoke helper and unit
  test files, and forbids workflow, dependency, migration, docs, scripts,
  repository-control, and credential-bearing files.
- `local_multi_file_task` policy narrows writes to
  `src/ai_org/adapters/codex/merge_candidate.py` and
  `tests/unit/test_codex_merge_candidate.py`, and forbids docs, workflow,
  dependency, migration, script, repository-control, and credential-bearing
  files.
- MergeCandidate summaries explicitly record no merge, no auto-merge, no
  auto-push, required human approval, and `waiting_merge_approval` state.
- Local real Codex execution is rejected if the main worktree changes during
  the task, even when the isolated task worktree diff is otherwise valid.
- The main-worktree fingerprint covers `HEAD`, porcelain status with all
  untracked files, tracked diffs, staged diffs, and untracked file content
  hashes. It is intended to catch dirty-file content changes even when status
  text is unchanged.
- Changed symlinks inside task worktrees that resolve outside the task worktree
  are rejected as file-policy violations.
- Prompt, diff, and command logs are sanitized before artifact persistence.
- Command logs expose logical `worktree://...` URIs and mask raw local worktree
  paths in Codex JSONL summaries.
- `SandboxRunner` isolates future command execution behind a port.
- `DockerSandboxRunner` defaults to non-root, disabled network, `cap-drop=ALL`,
  `no-new-privileges`, read-only root filesystem, explicit tmpfs, task worktree
  mount only, and CPU, memory, PID, timeout, stdout, and stderr limits.
- Sandbox policy rejects privileged containers, enabled network, root users,
  missing capability drops, writable root filesystems, secret-like environment
  keys, host mounts outside the task worktree, and dotenv or credential mounts.
- Default tests do not call real shell, real Codex, real LLM, or untrusted code.

## Known Risks

- Real Codex runtime is implemented only for a controlled local smoke test and
  controlled manual code tasks with fixed file scopes and no automatic merge.
- A prior real Codex multi-file validation modified the main worktree. That run
  is blocked and must not be treated as an accepted MergeCandidate.
- A later real Codex multi-file validation kept the main-worktree fingerprint
  stable but timed out during CLI exec. Timeout is blocked as
  `CODEX_CLI_TIMEOUT`; it cannot create an accepted MergeCandidate and must not
  be solved by increasing Codex permissions.
- MergeCandidate output can be misleading if reviewed out of context; later
  MergeService work must re-check policy, tests, and human approval before any
  branch operation.
- Docker sandboxing is implemented only as a foundation with fixed safe command
  tests; production arbitrary-code execution is not implemented.
- Worktree cleanup is manual in this stage.
- Role-level PostgreSQL grants are documented but not provisioned locally.
- Checkpoint cleanup is documented but not implemented.
- Mock clients do not represent every real external-runtime failure mode.

## Future Controls

- Network approval and egress policy before sandbox network access.
- Production image pinning/scanning before arbitrary code execution.
- Stronger permission and budget domain model.
- Separate database roles for application, checkpoint, and migration.
- Artifact retention and cleanup policy.
- Human-approved MergeService with re-validation before merge.
