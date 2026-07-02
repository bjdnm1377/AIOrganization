# Coding Worker Security

## Default Posture

The Coding Worker is controlled by the first-layer workflow. It cannot bypass
TaskSpec, WorkerRegistry, Review Worker, or audit logging. Default tests use only
Mock/DryRun clients and do not call real Codex, real LLMs, real shell execution,
or paid services. The local real Codex CLI path is a manual smoke test only and
requires `AI_ORG_ENABLE_REAL_CODEX_SMOKE=true`. The local real Codex small
code-task path is a separate manual test and requires
`AI_ORG_ENABLE_REAL_CODEX_CODE_TASK=true`.

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

`DiffCollector` records changed, created, deleted, and binary files; detects
forbidden file changes; detects oversized diffs; and flags simple secret markers
in diffs. Diff artifacts are sanitized before writing. `CommandLogCollector`
records command, cwd, exit code, stdout/stderr summary, duration, timeout,
network request flag, allowed flag, and approval flag. Logs are sanitized before
persistence.

`CodingTaskPromptRenderer` redacts secret-like task text before writing prompt
artifacts.

`LocalCodexCliClient` records only command summaries. It does not persist raw
environment variables, raw auth files, raw Codex doctor output, or absolute
worktree paths. Worktree paths in command stdout/stderr summaries are replaced
with `<worktree>`, and API-visible metadata uses `worktree://...` logical URIs.

The real CLI invocation uses `workspace-write` sandbox and `on-request`
approval. `danger-full-access`, sandbox bypass flags, automatic commits,
automatic merges, and unrestricted file scope are not used.

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

## Review Gate

The independent `MockReviewWorker` rejects Codex results with policy violations,
NOT_CONFIGURED real-runtime status, or suspicious diff markers. Failed coding
tests produce bounded rework until `max_attempts` is reached, after which the
workflow blocks the task/project.

## Remaining Risks

- Real Codex smoke execution uses the local user's existing Codex CLI session
  and can consume real Codex service capacity when manually enabled.
- Real Codex small code-task execution also uses the local user's Codex CLI
  session when manually enabled.
- The smoke test does not expose every failure mode of a production Coding
  Worker.
- The Docker sandbox foundation is not a production-grade arbitrary-code
  execution environment.
- Policy is intentionally simple and deterministic; a stronger permission model
  is required before real untrusted code execution.
