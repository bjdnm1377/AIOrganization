# Coding Worker Security

## Default Posture

The Coding Worker is controlled by the first-layer workflow. It cannot bypass
TaskSpec, WorkerRegistry, Review Worker, or audit logging. Default tests use only
Mock/DryRun clients and do not call real Codex, real LLMs, real shell execution,
or paid services. The local real Codex CLI path is a manual smoke test only and
requires `AI_ORG_ENABLE_REAL_CODEX_SMOKE=true`. The local real Codex small
code-task path is a separate manual test and requires
`AI_ORG_ENABLE_REAL_CODEX_CODE_TASK=true`. The controlled real Codex multi-file
task path is manual-only and requires
`AI_ORG_ENABLE_REAL_CODEX_MULTI_FILE_TASK=true`. The controlled real Codex
stepwise multi-file path is also manual-only and requires
`AI_ORG_ENABLE_REAL_CODEX_STEPWISE_MULTI_FILE_TASK=true`. The current CLI
diagnostic path is manual-only and requires
`AI_ORG_ENABLE_REAL_CODEX_DIAGNOSTICS=true`; it uses an independent temporary
Git repository and never enters MergeCandidate or MergeService behavior.

## Policy Checks

`CodingWorkerPolicy` reads task metadata for:

- allowed and forbidden files;
- allowed and forbidden commands;
- required tests;
- deterministic Mock/DryRun simulation flags.

Task metadata can add forbidden file patterns, but it cannot remove the system
baseline forbidden files such as `.github/**`, `alembic/**`, `pyproject.toml`,
and `requirements-lock.txt`.

When `codex_mode="local_cli"`, the policy narrows the default allowed file set
to `smoke/**` and adds smoke-stage forbidden patterns including `.git/**`,
`src/**`, `tests/**`, `docs/**`, `.github/**`, `requirements*.txt`,
`pyproject.toml`, `alembic/**`, `AGENTS.md`, and `README.md`. Task metadata
cannot widen the real CLI allowed file scope beyond `smoke/**`.

When `codex_mode="local_code_task"`, the policy narrows writes to:

- `src/ai_org/adapters/codex/smoke_helpers.py`
- `tests/unit/test_codex_smoke_helpers.py`

It also forbids `.git/**`, `.github/**`, `.env*`, dependency locks,
`pyproject.toml`, migrations, docs, `AGENTS.md`, `README.md`,
`docker-compose.yml`, and `scripts/**`. Task metadata cannot widen this real
code-task scope.

When `codex_mode="local_multi_file_task"`, the policy narrows writes to:

- `src/ai_org/adapters/codex/merge_candidate.py`
- `tests/unit/test_codex_merge_candidate.py`

It forbids repository control files, workflow files, dependency files,
migrations, docs, scripts, environment files, `AGENTS.md`, `README.md`, and
production config. Task metadata cannot widen this multi-file scope.

When `codex_mode="local_stepwise_multi_file_task"`, the logical final scope is
the same two files, but `CodexWorker` executes fixed single-file steps. Step 1
may modify only `src/ai_org/adapters/codex/merge_candidate.py` and forbids
`tests/**`; Step 2 may modify only `tests/unit/test_codex_merge_candidate.py`
and forbids `src/**`. Task metadata cannot widen either step.

`DiffCollector` records changed, created, deleted, and binary files; detects
forbidden file changes; detects oversized diffs; and flags simple secret markers
in diffs. Diff artifacts are sanitized before writing. `CommandLogCollector`
records command, cwd, exit code, stdout/stderr summary, duration, timeout,
network request flag, allowed flag, and approval flag. Logs are sanitized before
persistence.

For local real Codex modes, `CodexWorker` compares a main-worktree fingerprint
before and after execution. The fingerprint covers the current `HEAD`,
`git status --porcelain=v1 --untracked-files=all`, tracked diffs, staged diffs,
and untracked file content hashes. Any main worktree change forces the result to
FAILED with `MAIN_WORKTREE_MODIFIED` and a `main_worktree:modified` policy
violation, even if the task worktree diff itself looks valid. This includes
dirty files whose `git status --short` output stays unchanged while their
contents change.

`DiffCollector` runs against the task worktree, not the main worktree. It also
rejects changed symlinks that resolve outside the task worktree, including
symlinks that point back to the main repository or other host paths.

`CodingTaskPromptRenderer` redacts secret-like task text before writing prompt
artifacts.

`LocalCodexCliClient` records only command summaries. It does not persist raw
environment variables, raw auth files, raw Codex doctor output, or absolute
worktree paths. Worktree paths in command stdout/stderr summaries are replaced
with `<worktree>`, and API-visible metadata uses `worktree://...` logical URIs.

The real CLI invocation uses `workspace-write` sandbox and `on-request`
approval. `danger-full-access`, sandbox bypass flags, automatic commits,
automatic merges, and unrestricted file scope are not used.

Codex CLI exec timeout is a blocking runtime failure. Timeout command logs
record `timeout_type`, elapsed time, JSONL event counts, last observed JSONL
event type, whether an approval request was observed, whether network was
requested, and whether the process tree was killed. Timeout results keep
running the main-worktree fingerprint post-check, do not produce accepted
MergeCandidate artifacts, and are rejected by the Review Worker with
`codex:timeout`. In the stepwise multi-file path, a per-step Codex exec timeout
is normalized to `CODEX_STEP_TIMEOUT`, records the failed step index, stops all
later steps, keeps the main-worktree fingerprint post-check, and is rejected by
the Review Worker.

Codex CLI diagnostics classify timeouts without accepting work. The diagnostic
runner records no-output, total-timeout, thread/turn/item stall, approval-wait,
transport-stall, and process-exit-without-completion signals from bounded JSONL
summaries. A diagnostic timeout is reported as
`CODEX_CLI_DIAGNOSTIC_TIMEOUT`, does not generate a MergeCandidate, does not run
merge or push code, and is rejected by the Review Worker as `codex:timeout`.

## Docker Sandbox Foundation

The sandbox layer is implemented behind a `SandboxRunner` port. Default tests can
use `MockSandboxRunner`; Docker integration tests use `DockerSandboxRunner` with
fixed safe commands only.

`DockerSandboxRunner` rejects privileged mode, root users, enabled network,
missing `cap-drop=ALL`, missing `no-new-privileges`, writable root filesystems,
secret-like environment keys, host mounts outside the task worktree, and dotenv,
SSH, Git, or cloud credential mounts. The runner uses `--network none`, a
read-only root filesystem, explicit `/tmp` tmpfs, non-root user
`65532:65532`, and CPU, memory, PID, timeout, stdout, and stderr limits.

`CodexWorker` can optionally run a sandbox smoke hook when
`sandbox_smoke=True`; it records a `sandbox.health` command log. For the manual
small real code task, `sandbox_test_profile="real_code_task_smoke"` records a
fixed `sandbox.test` command after Codex returns. Neither path executes
task-provided shell commands, and real Codex execution is not moved into Docker.
For the controlled multi-file task,
`sandbox_test_profile="real_multi_file_task_merge_candidate"` records a fixed
`sandbox.test` command that imports the MergeCandidate module and verifies the
expected test file exists.

For the controlled stepwise multi-file task,
`sandbox_test_profile="real_stepwise_multi_file_task_merge_candidate"` records a
fixed `sandbox.test` command:
`python -m pytest tests/unit/test_codex_merge_candidate.py -q`.

## Review Gate

The independent `MockReviewWorker` rejects Codex results with policy violations,
NOT_CONFIGURED real-runtime status, or suspicious diff markers. Failed coding
tests produce bounded rework until `max_attempts` is reached, after which the
workflow blocks the task/project.

For MergeCandidate output, the Review Worker rejects summaries that indicate a
merge, auto-merge, auto-push, missing human approval, or any state other than
`waiting_merge_approval`.

## Human-Approved Merge Controls

The merge approval foundation is independent from real Codex execution. It can
be exercised with Mock, DryRun, or manual fixture candidates while real Codex
multi-file and diagnostic write paths remain blocked by timeout.

`MergeApprovalService` accepts only reviewed candidates that are still
`WAITING_APPROVAL`, require human approval, and do not request auto-merge or
auto-push. Rejected, blocked, merged, duplicate, or blocked-real-Codex fixture
candidates return conflict errors instead of silently transitioning.

`MergeService` requires an approved candidate, a clean target repository, and
`HEAD == base_commit`. It blocks high-risk files such as `.git/**`,
`.github/**`, `.env*`, dependency files, `pyproject.toml`, `alembic/**`, and
`scripts/**`. It also blocks patches containing local absolute paths or
secret-like values, and blocks patch files that are not listed in the
candidate's reviewed `changed_files`. Patch application and tests happen in a
temporary integration clone, not in the current AIleader master worktree by
default.

Successful controlled merge results write audit events and keep
`auto_push=False` and `auto_deploy=False`. The service does not push, deploy,
open PRs, or execute real Codex.

## Remaining Risks

- Real Codex smoke execution uses the local user's existing Codex CLI session
  and can consume real Codex service capacity when manually enabled.
- Real Codex small code-task execution also uses the local user's Codex CLI
  session when manually enabled.
- Real Codex multi-file execution uses the local user's Codex CLI session when
  manually enabled and must remain limited to a pending MergeCandidate summary.
- Real Codex stepwise multi-file execution also uses the local user's Codex CLI
  session when manually enabled. It reduces one logical multi-file task into
  multiple single-file steps, but still relies on the local Codex CLI runtime.
- Real Codex CLI diagnostics also use the local user's Codex CLI session when
  manually enabled. They isolate CLI/app-server/auth/transport failure modes
  before any new Coding Worker task is attempted.
- A previous real Codex multi-file validation changed the main worktree outside
  the task worktree. That result is not accepted; the main-worktree fingerprint
  guard is a fail-closed control and must be revalidated before any merge stage.
- A later real Codex multi-file validation kept the main-worktree fingerprint
  stable but timed out during CLI exec. The current recovery path is to reduce
  real task complexity and preserve timeout diagnostics, not to increase
  permissions or relax isolation.
- The smoke test does not expose every failure mode of a production Coding
  Worker.
- The Docker sandbox foundation is not a production-grade arbitrary-code
  execution environment.
- Policy is intentionally simple and deterministic; a stronger permission model
  is required before real untrusted code execution.
