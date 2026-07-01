# Coding Worker Security

## Default Posture

The Coding Worker is controlled by the first-layer workflow. It cannot bypass
TaskSpec, WorkerRegistry, Review Worker, or audit logging. Default tests use only
Mock/DryRun clients and do not call real Codex, real LLMs, real shell execution,
or paid services.

## Policy Checks

`CodingWorkerPolicy` reads task metadata for:

- allowed and forbidden files;
- allowed and forbidden commands;
- required tests;
- deterministic Mock/DryRun simulation flags.

Task metadata can add forbidden file patterns, but it cannot remove the system
baseline forbidden files such as `.github/**`, `alembic/**`, `pyproject.toml`,
and `requirements-lock.txt`.

`DiffCollector` records changed, created, deleted, and binary files; detects
forbidden file changes; detects oversized diffs; and flags simple secret markers
in diffs. Diff artifacts are sanitized before writing. `CommandLogCollector`
records command, cwd, exit code, stdout/stderr summary, duration, timeout,
network request flag, allowed flag, and approval flag. Logs are sanitized before
persistence.

`CodingTaskPromptRenderer` redacts secret-like task text before writing prompt
artifacts.

## Review Gate

The independent `MockReviewWorker` rejects Codex results with policy violations,
NOT_CONFIGURED real-runtime status, or suspicious diff markers. Failed coding
tests produce bounded rework until `max_attempts` is reached, after which the
workflow blocks the task/project.

## Remaining Risks

- Real Codex runtime is not implemented.
- A production sandbox is not implemented.
- Policy is intentionally simple and deterministic; a stronger permission model
  is required before real untrusted code execution.
