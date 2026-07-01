# Docker Sandbox Acceptance Report

Status: PENDING FINAL CI VERIFICATION

## 1. Stage Goal

Implement a Docker sandbox foundation for future Coding Worker command
execution without calling real Codex in CI, without executing user-provided
untrusted code, and without automatic merge.

## 2. Current Status

Implementation and local Docker verification are complete. Final GitHub Actions
verification is pending for the stage commit.

## 3. Completed Content

- Added `SandboxRunner` port and structured sandbox command/result models.
- Added `SandboxPolicy`, `SandboxNetworkPolicy`, `SandboxMountPolicy`,
  `SandboxResourceLimits`, and `SandboxAuditEvent`.
- Added `MockSandboxRunner`.
- Added `DockerSandboxRunner`.
- Added sandbox policy validation for privileged mode, root user, network,
  capability drops, root filesystem mode, host mounts, credential mounts,
  secret-like environment keys, and resource limits.
- Added primary worktree mount validation so home and credential-bearing paths
  cannot be mounted as the sandbox workspace.
- Added bounded Docker stdout/stderr readers that terminate the container when
  output exceeds configured limits.
- Added optional `CodexWorker` sandbox smoke hook using `sandbox_smoke=True`.
- Added Docker sandbox unit and integration tests.
- Added explicit GitHub Actions Docker sandbox integration step.
- Updated documentation.

## 4. Not Completed

- Real Codex execution inside Docker.
- Arbitrary user-code execution.
- Network approval and egress allowlists.
- Production image digest pinning and image vulnerability scanning.
- Automatic merge or apply of worktree changes.
- Automatic worktree or container artifact cleanup.

## 5. SandboxRunner Architecture

The application uses a `SandboxRunner` port. The domain model does not import
Docker, subprocess, FastAPI, LangGraph, or SQLAlchemy types. Concrete adapters
live under `src/ai_org/adapters/sandbox/`.

## 6. DockerSandboxRunner Security Configuration

Default Docker controls:

- non-root user `65532:65532`;
- no privileged mode;
- `--cap-drop ALL`;
- `--security-opt no-new-privileges`;
- read-only root filesystem;
- explicit `/tmp` tmpfs;
- explicit `/workspace` working directory;
- task worktree bind mount only;
- no home, SSH, Git credential, cloud credential, `.env`, or Docker socket
  mount;
- no host PID or IPC flags;
- `--network none`;
- CPU, memory, PID, timeout, stdout, and stderr limits;
- sanitized stdout and stderr summaries.

## 7. MockSandboxRunner Behavior

`MockSandboxRunner` validates the same policy, returns deterministic structured
results, and supports an unavailable mode returning `BLOCKED`.

## 8. Network Policy

Network is disabled by default. A policy with `network.enabled=True` is rejected
because approval and egress control are not implemented in this stage.

## 9. Mount Policy

Only the task worktree is mounted by default. Extra mounts outside the worktree,
dotenv files, SSH paths, Git credential paths, cloud credential paths, and other
host credential paths are rejected.

## 10. Resource Limits

Default limits:

- CPU: `1.0`;
- memory: `512m`;
- PIDs: `128`;
- timeout: `120` seconds;
- stdout limit: `65536` bytes;
- stderr limit: `65536` bytes.

The timeout integration test uses a one-second limit to verify timeout handling.

## 11. Command Log Sanitization

Sandbox stdout and stderr are bounded while the process runs; output-limit
violations kill the container and return `SANDBOX_OUTPUT_LIMIT_EXCEEDED`.
Summaries are passed through the project redaction helper before being returned.
Worktree paths are replaced with `<worktree>`. Secret-like environment keys are
rejected before Docker is invoked.

## 12. CodexWorker Integration Status

`CodexWorker` accepts an optional `SandboxRunner`. It only invokes the sandbox
when task metadata contains `sandbox_smoke=True`; the command is fixed and
recorded as `sandbox.health`. Task-provided commands are not executed through
this hook.

## 13. Docker Local Detection Result

Local Docker is available:

- Docker Client/Server observed: Docker Desktop `29.2.1`.
- Local Docker sandbox integration result:
  `.venv\Scripts\python.exe -m pytest tests\integration\test_docker_sandbox.py -q`
  returned exit `0`, `5 passed`.

## 14. Local Test Commands

| Command | Exit | Result |
| --- | ---: | --- |
| `.venv\Scripts\python.exe -m ruff format src tests` | 0 | 60 files left unchanged |
| `.venv\Scripts\python.exe -m ruff check src tests` | 0 | All checks passed |
| `.venv\Scripts\python.exe -m mypy src tests` | 0 | Success: no issues found in 60 source files |
| `.venv\Scripts\python.exe -m pytest tests\unit\test_sandbox_policy.py tests\integration\test_docker_sandbox.py -q` | 0 | 16 passed |
| `.venv\Scripts\python.exe -m pytest -q` | 0 | 70 passed, 1 skipped, 1 warning |
| `powershell -ExecutionPolicy Bypass -File scripts\supply_chain_checks.ps1 -Python .\.venv\Scripts\python.exe` | 0 | pip-audit, license report, SBOM, and detect-secrets completed |
| `git diff --check` | 0 | no whitespace errors |

Supply-chain summary:

- `pip-audit`: 106 dependencies, 0 known vulnerabilities.
- `pip-licenses`: 103 package license entries.
- CycloneDX SBOM: 107 components.
- `detect-secrets`: 0 findings.

## 15. CI Result

Pending for this stage commit.

## 16. Reviewer Findings And Handling

Independent Reviewer findings and handling:

- Medium: Docker stdout/stderr limits were applied after process completion, so
  a command could emit large output into runner memory before truncation. Fixed
  by replacing `subprocess.run(capture_output=True)` with bounded stdout/stderr
  readers that terminate Docker on output-limit violation. Added integration
  coverage for `SANDBOX_OUTPUT_LIMIT_EXCEEDED`.
- Medium: `worktree_path` itself could point at home or credential-bearing host
  paths, while credential checks only covered extra mounts. Fixed by rejecting
  home and credential-bearing primary worktree mounts. Added unit tests for
  home and `.ssh` primary mount rejection.

No high-severity findings were reported. The Reviewer confirmed CI keeps
`AI_ORG_ENABLE_REAL_CODEX_SMOKE=false`, the CodexWorker sandbox hook uses a
fixed command rather than task-provided commands, and the documentation describes
this as a foundation rather than production arbitrary-code sandboxing.

## 17. Known Risks

- This is not production-grade arbitrary-code sandboxing.
- Docker image is referenced as `python:3.12-slim` for integration tests; a
  later production stage should pin by digest and scan image vulnerabilities.
- Network approval and egress control are not implemented.
- Real Codex execution is not routed through Docker yet.
- Worktree cleanup remains manual.

## 18. Next Stage Recommendation

After CI passes and user accepts this stage, proceed to a small real Codex Worker
code modification routed through the sandbox runner for formatter/test commands.

## 19. Git State

- Current branch: `master`
- Current commit hash: pending final commit
- `git status --short`: pending final capture

## 20. User Acceptance Options

- Pass: enter real Codex Worker plus Docker sandbox small code modification
  stage.
- Wait: keep sandbox foundation implemented but do not proceed.
- Reject: continue fixing Docker sandbox foundation.
- Pause: stop for now.
- Adjust target: re-plan the next stage.
