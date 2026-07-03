# Docker Sandbox

## Implemented

This stage adds a sandbox foundation for future Coding Worker command
execution. It does not execute user-provided untrusted code and it is not a
production-grade sandbox yet.

Implemented components:

- `SandboxRunner` port.
- `SandboxCommandSpec` and `SandboxCommandResult`.
- `SandboxPolicy`, `SandboxNetworkPolicy`, `SandboxMountPolicy`, and
  `SandboxResourceLimits`.
- `MockSandboxRunner` for deterministic tests without Docker.
- `DockerSandboxRunner` for fixed safe integration tests.
- Optional `CodexWorker` sandbox smoke hook through `sandbox_smoke=True`.

## Default Docker Controls

`DockerSandboxRunner` validates policy before running Docker and uses these
defaults:

- non-root user `65532:65532`;
- no `--privileged`;
- `--cap-drop ALL`;
- `--security-opt no-new-privileges`;
- read-only root filesystem;
- explicit tmpfs at `/tmp`;
- explicit working directory `/workspace`;
- only the task worktree mounted at `/workspace`;
- no user home mount;
- no SSH agent mount;
- no Git credential mount;
- no cloud credential mount;
- no `.env` mount;
- no Docker socket mount;
- no host PID or IPC options;
- network disabled with `--network none`;
- CPU, memory, PID, timeout, stdout, and stderr limits;
- stdout and stderr summaries are redacted before being returned.
- stdout and stderr limits are enforced while Docker is running; exceeding a
  limit terminates the container and returns `SANDBOX_OUTPUT_LIMIT_EXCEEDED`.

## Network Policy

Network is disabled by default. A `SandboxPolicy` with
`network.enabled=True` is rejected in this stage because the approval and egress
policy flow is not implemented yet.

## Mount Policy

The worktree is the only default bind mount. Extra mounts are rejected unless
they resolve inside the task worktree. Dotenv, SSH, Git credential, cloud
credential, and other host credential paths are blocked.

## Codex Worker Integration

`CodexWorker` accepts an optional `SandboxRunner`. It invokes the sandbox only
for fixed profiles:

- `sandbox_smoke=True` runs a fixed health command and records `sandbox.health`.
- `sandbox_test_profile="real_code_task_smoke"` runs a fixed Python assertion
  command after the small real Codex code task and records `sandbox.test`.
- `sandbox_test_profile="real_multi_file_task_merge_candidate"` runs a fixed
  Python assertion command after the controlled multi-file Codex task and
  records `sandbox.test`.

The sandbox test profile sets `PYTHONDONTWRITEBYTECODE=1` and does not execute
task-provided shell commands. Real Codex is invoked by the local CLI client in
the task worktree, not inside Docker.

The current controlled multi-file sandbox test validates only the generated
MergeCandidate module and its unit test. Documentation files are outside the
real Codex multi-file allowed scope and are not required by this fixed sandbox
command.

The human-approved merge foundation does not call real Codex and does not
execute arbitrary user-provided sandbox commands. Its unit tests use temporary
Git repositories and explicit test commands. Docker sandbox policy tests remain
separate and must continue to pass before the merge foundation is accepted.

## Test Coverage

Unit tests cover policy defaults, privileged rejection, network rejection, host
mount rejection, credential mount rejection, resource limits, command-log
redaction, unavailable sandbox behavior, `MockSandboxRunner`, and optional
`CodexWorker` integration.

Docker integration tests run fixed commands with `DockerSandboxRunner`, verify a
successful safe command, forbidden mount blocking, timeout behavior, output
limits, and redaction. Local Docker unavailability produces an explicit skip.
GitHub Actions treats Docker unavailability as a failure for the Docker sandbox
integration step.

## Not Implemented

- Real untrusted-code execution.
- Codex command execution inside Docker.
- Arbitrary task-provided test commands.
- Network approval and egress allowlists.
- Production image digest pinning and image vulnerability scanning.
- Worktree cleanup automation.
- Automatic merge of sandbox results.
- Automatic merge approval or branch merge.
- Automatic push or deploy from merge approval results.
