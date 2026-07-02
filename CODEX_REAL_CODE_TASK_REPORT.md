# Real Codex Small Code Task Report

Status: WAITING FOR USER APPROVAL

This is the local verification report for the real Codex small code-task stage.
Remote GitHub Actions verification is still required before this report can be
promoted to `Status: VERIFIED COMPLETE FOR REAL CODEX SMALL CODE TASK`.

## 1. Stage Goal

Verify that a real local Codex CLI Coding Worker can complete one extremely
small, controlled, auditable, reversible code task inside a task-scoped Git
worktree, with Docker sandbox validation, independent review, sanitized
artifacts, no main-branch modification, no automatic commit, and no automatic
merge.

## 2. Current Status

- Local implementation complete.
- Local default CI-equivalent checks complete.
- Manual real Codex small code-task test complete.
- Remote GitHub Actions CI not yet run for these changes.
- Do not enter the next stage until GitHub Actions passes.

## 3. Codex CLI Detection

- Codex CLI detected: yes.
- Codex CLI version: `codex-cli 0.135.0`.
- `codex doctor --json`: preflight passed; raw auth details were not persisted
  in this report.
- Opt-in used for manual test: `AI_ORG_ENABLE_REAL_CODEX_CODE_TASK=true`.
- Default and CI opt-in: `AI_ORG_ENABLE_REAL_CODEX_CODE_TASK=false`.
- Login or authorization required during this run: no.

## 4. Real Code Task

The manual task asked Codex to create exactly two files:

- `src/ai_org/adapters/codex/smoke_helpers.py`
- `tests/unit/test_codex_smoke_helpers.py`

The helper implements `format_smoke_metadata(metadata: dict[str, object]) ->
str`. The test file checks empty metadata and sorted primitive formatting.

## 5. TaskSpec Summary

- `worker_type`: `codex`
- `codex_mode`: `local_code_task`
- `codex_sandbox`: `workspace-write`
- `codex_approval_policy`: `on-request`
- `sandbox_test_profile`: `real_code_task_smoke`
- `max_attempts`: `1`
- acceptance criteria: independent review of the real Codex code task.

## 6. Allowed And Forbidden Files

Allowed files:

- `src/ai_org/adapters/codex/smoke_helpers.py`
- `tests/unit/test_codex_smoke_helpers.py`

Forbidden files include `.git/**`, `.github/**`, `.env*`, requirements files,
`pyproject.toml`, `alembic/**`, `docs/**`, `AGENTS.md`, `README.md`,
`docker-compose.yml`, and `scripts/**`.

Task metadata cannot widen the real code-task allowed file set.

## 7. Worktree And Branch

- Logical worktree URI:
  `worktree://codex/task_d1a194a5cf8843d9a3ee89a2d3872113/attempt-1`
- Branch name:
  `ai-org/codex/b0d6a6028931/89a2d3872113-1`
- Base commit:
  `f38835c5ea95bb304dfe0a47507d6368951ca96a`
- Main branch modified by Codex: no.
- Automatic merge: no.
- Automatic commit of Codex output branch: no.
- Automatic push of Codex output branch: no.

## 8. Changed Files And Diff Summary

Changed files in the task worktree:

- `src/ai_org/adapters/codex/smoke_helpers.py`
- `tests/unit/test_codex_smoke_helpers.py`

Diff summary:

- 2 files changed.
- 49 insertions.
- 0 deletions.
- No binary files.
- No forbidden file violations.
- No command violations.
- No detected secret patterns.

## 9. Sandbox Validation

Sandbox runner used: `DockerSandboxRunner`.

Sandbox policy summary:

- non-root user;
- no privileged mode;
- `--cap-drop ALL`;
- `no-new-privileges`;
- read-only root filesystem;
- explicit `/tmp` tmpfs;
- only task worktree mounted;
- network disabled;
- CPU, memory, PID, timeout, stdout, and stderr limits;
- `PYTHONDONTWRITEBYTECODE=1`.

Fixed sandbox command result:

- command log entry: `sandbox.test`
- status: `SUCCEEDED`
- exit code: `0`
- network requested: `false`
- duration: `982 ms`

## 10. Command Logs Summary

Sanitized command log entries:

- `codex --version`: completed, exit `0`.
- `codex doctor --json`: completed, exit `0`, preflight passed.
- `codex --sandbox workspace-write --ask-for-approval on-request exec --json --cd <worktree> --color never -`:
  completed, exit `0`, summarized JSONL only.
- `sandbox.test`: `SUCCEEDED`, exit `0`.

No raw auth file content, environment variables, tokens, absolute worktree
paths, or raw Codex JSONL payloads were written to this report.

## 11. Artifacts

Logical artifact URIs produced by the workflow:

- `artifact://codex/task_d1a194a5cf8843d9a3ee89a2d3872113/attempt-1/prompt.md`
- `artifact://codex/task_d1a194a5cf8843d9a3ee89a2d3872113/attempt-1/command-log.json`
- `artifact://codex/task_d1a194a5cf8843d9a3ee89a2d3872113/attempt-1/diff.patch`

Artifact paths are not exposed through API-visible metadata.

## 12. Secret Sanitization

Implemented and tested:

- OpenAI-style `sk-...` redaction.
- GitHub token redaction.
- Bearer token redaction.
- private key block redaction.
- Windows and common POSIX absolute path replacement.
- diff secret-pattern counting for OpenAI, GitHub, Bearer, private-key, and
  marker strings.

Local `detect-secrets` result: 0 findings.

## 13. Review Worker Decision

Manual real code-task workflow result:

- Project status: `COMPLETED`.
- Task status: `ACCEPTED`.
- Review Worker decision: accepted.
- WorkerRun count for Codex: 1.
- Codex execution repeated for the same workflow run: no.

Reviewer sub-agent findings:

- High: none.
- Medium 1: sandbox post-test could run for mock or not-configured results.
  Fixed by gating sandbox test on `policy.mode == "local_code_task"` and
  successful Codex result.
- Medium 2: stage report missing and Roadmap had early completion wording.
  Fixed by creating this report and moving Roadmap language to current-stage
  wording until CI passes.
- Medium 3: artifact redaction did not cover enough token/path shapes. Fixed by
  expanding shared redaction and diff secret detection.
- Low findings: added `local_code_task` coverage for forbidden file rejection
  and `danger-full-access` rejection; updated generic failure wording.

## 14. FastAPI Query Verification

FastAPI e2e tests remain part of the default test suite and passed locally.
The manual real code-task test uses the application service and LangGraph
workflow directly, not a running HTTP server.

## 15. Local Test Commands

| Command | Exit | Result |
| --- | ---: | --- |
| `.venv\Scripts\python.exe -m ruff format .` | 0 | 64 files left unchanged |
| `.venv\Scripts\python.exe -m ruff check .` | 0 | All checks passed |
| `.venv\Scripts\python.exe -m mypy src tests` | 0 | Success: no issues found in 61 source files |
| `.venv\Scripts\python.exe -m pytest tests\unit\test_codex_worker.py tests\manual\test_real_codex_code_task.py -q` | 0 | 30 passed, 1 skipped |
| `$env:AI_ORG_ENABLE_REAL_CODEX_CODE_TASK='true'; .venv\Scripts\python.exe -m pytest tests\manual\test_real_codex_code_task.py -q` | 0 | 1 passed |
| `.venv\Scripts\python.exe -m pytest -q` | 0 | 81 passed, 1 skipped, 1 warning |
| `.\scripts\supply_chain_checks.ps1` | 0 | pip-audit: no known vulnerabilities; detect-secrets: 0 findings; license report and SBOM generated |
| `git diff --check` | 0 | no whitespace errors |

## 16. CI Verification

Remote CI for these changes: pending.

Expected workflow:

- `.github/workflows/verification.yml`
- Python 3.12
- PostgreSQL service `postgres:16.6`
- real Codex disabled with
  `AI_ORG_ENABLE_REAL_CODEX_SMOKE=false` and
  `AI_ORG_ENABLE_REAL_CODEX_CODE_TASK=false`

This section must be updated with CI run id, run URL, commit hash, and
conclusion after push.

## 17. Known Risks

- Manual real Codex code-task execution uses the local Codex CLI session and may
  consume real Codex service capacity.
- The Docker sandbox still runs only fixed commands and is not production
  arbitrary-code sandboxing.
- Codex output worktrees are retained for manual inspection and cleanup.
- No automatic merge approval workflow is implemented yet.

## 18. Unfinished Content

- Remote GitHub Actions verification for this stage.
- Automatic worktree retention cleanup.
- Human merge approval workflow.
- Production arbitrary-code sandbox hardening.

## 19. Next Stage Recommendation

After remote CI passes and the user accepts this stage, proceed to controlled
multi-file code tasks with explicit human merge approval.

## 20. Git State

- Current branch: `master`
- Current implementation base commit:
  `f38835c5ea95bb304dfe0a47507d6368951ca96a`
- Stage commit hash: pending commit.
- `git status --short`: pending final capture after commit.

## 21. User Acceptance Options

- Pass: enter controlled multi-file code task and human merge approval stage.
- Wait: keep this stage pending until remote CI evidence is available.
- Reject: continue fixing the real Codex small code-task stage.
- Pause: stop for now.
- Adjust target: re-plan the next stage.
