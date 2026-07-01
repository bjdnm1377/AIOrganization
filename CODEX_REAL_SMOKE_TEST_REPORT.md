# Controlled Real Codex Smoke Test Report

Status: BLOCKED - GITHUB PUSH NETWORK UNAVAILABLE

## 1. Stage Goal

Extend `LocalCodexCliClient` from a NOT_CONFIGURED-only stub into an explicit
opt-in local Codex CLI smoke path, while keeping Codex behind TaskSpec,
WorkerRegistry, task-scoped Git worktrees, independent review, audit records,
and artifact query boundaries.

## 2. Current Status

Local controlled real Codex smoke test passed. GitHub Actions verification for
the new implementation commit has not started because the local environment
cannot currently connect to `github.com:443` for Git push.

## 3. Codex CLI Detection

- Codex CLI detected: yes.
- Version command: `codex --version`
- Version result: `codex-cli 0.135.0`
- Readiness preflight: `codex doctor --json`
- Doctor summary persisted by worker: coarse preflight passed; no auth details
  persisted.
- Raw auth files, tokens, and raw doctor output were not written to repo reports
  or artifacts.

## 4. Opt-In

- Required environment variable: `AI_ORG_ENABLE_REAL_CODEX_SMOKE=true`
- Default behavior without opt-in: `NOT_CONFIGURED`
- CI behavior: the variable is not set, so CI does not call real Codex.

## 5. Smoke Task

- Worker type: `codex`
- Mode: `local_cli`
- Allowed files: `smoke/**`
- Expected changed file: `smoke/codex_worker_smoke.txt`
- Forbidden files include `.git/**`, `.github/**`, `.env*`,
  `requirements*.txt`, `pyproject.toml`, `alembic/**`, `src/**`, `tests/**`,
  `docs/**`, `AGENTS.md`, and `README.md`.

TaskSpec summary:

```json
{
  "worker_type": "codex",
  "metadata": {
    "codex_mode": "local_cli",
    "allowed_files": ["smoke/**"],
    "codex_sandbox": "workspace-write",
    "codex_approval_policy": "on-request"
  }
}
```

## 6. Execution Boundary

Actual command shape:

```text
codex --sandbox workspace-write --ask-for-approval on-request exec --json --cd <worktree> --color never -
```

- Prompt passed through stdin.
- `cwd` and `--cd` point to the task worktree.
- No `danger-full-access`.
- No sandbox bypass flags.
- No automatic commit, merge, or push.
- Worktree path in API-visible metadata: `worktree://codex/{task_id}/attempt-1`.

## 7. Local Real Smoke Result

Manual command:

```powershell
$env:AI_ORG_ENABLE_REAL_CODEX_SMOKE='true'; .\.venv\Scripts\python.exe -m pytest tests\manual\test_real_codex_smoke.py -q
```

Result:

- Exit code: `0`
- Pytest result: `1 passed in 160.03s (0:02:40)`
- Smoke task id: `task_abfff59647384968b293e482a713f31f`
- Worktree branch: `ai-org/codex/358a53d4e28d/e482a713f31f-1`
- Base/head commit in the temporary smoke repo: `1b7d15e26f3c02c42b1ba72810dc717c6fbfb806`
- Changed files: `["smoke/codex_worker_smoke.txt"]`
- Diff summary: one new smoke text file; no source, test, dependency, workflow,
  docs, or migration changes.
- Review Worker decision: accepted.
- Main branch modified: no.
- Automatic merge: no.

Final smoke diff:

```diff
diff --git a/smoke/codex_worker_smoke.txt b/smoke/codex_worker_smoke.txt
new file mode 100644
--- /dev/null
+++ b/smoke/codex_worker_smoke.txt
@@ -0,0 +1,3 @@
+AI Organization Codex real smoke test
+task_abfff59647384968b293e482a713f31f
+no secrets
```

## 8. Command Logs Summary

The worker persisted sanitized summaries only:

- `codex --version`: exit `0`, stdout `codex-cli 0.135.0`
- `codex doctor --json`: exit `0`, `network_requested=true`, coarse preflight
  summary only
- `codex --sandbox workspace-write --ask-for-approval on-request exec --json --cd <worktree> --color never -`: exit `0`, `network_requested=true`

Codex JSONL output was summarized as event counts only and completed
successfully. Raw session/thread identifiers, raw auth details, and local
absolute paths were not persisted in command-log summaries.

## 9. Artifacts

Artifact URIs use logical values:

- `artifact://codex/{task_id}/attempt-1/prompt.md`
- `artifact://codex/{task_id}/attempt-1/command-log.json`
- `artifact://codex/{task_id}/attempt-1/diff.patch`

No API response or committed report includes raw checkpoint payloads, auth
tokens, API keys, raw Codex auth files, or internal exception tracebacks.

## 10. FastAPI And Audit

FastAPI WorkerRun/artifact query endpoints were already implemented in the prior
stage and remain covered by tests. The real smoke manual test validates the same
application workflow path and asserts that `coding_worker.completed` audit event
is written.

## 11. Local Test Commands

| Command | Exit | Result |
| --- | ---: | --- |
| `.venv\Scripts\python.exe -m ruff format .` | 0 | 56 files left unchanged |
| `.venv\Scripts\python.exe -m ruff check .` | 0 | All checks passed |
| `.venv\Scripts\python.exe -m mypy src tests` | 0 | Success: no issues found in 53 source files |
| `.venv\Scripts\python.exe -m pytest tests\unit\test_codex_worker.py tests\manual\test_real_codex_smoke.py -q` | 0 | 19 passed, 1 skipped |
| `$env:AI_ORG_ENABLE_REAL_CODEX_SMOKE='true'; .\.venv\Scripts\python.exe -m pytest tests\manual\test_real_codex_smoke.py -q` | 0 | 1 passed in 160.03s |
| `.venv\Scripts\python.exe -m pytest -q` | 0 | 54 passed, 1 skipped, 1 warning |
| `powershell -ExecutionPolicy Bypass -File scripts\supply_chain_checks.ps1 -Python .\.venv\Scripts\python.exe` | 0 | pip-audit, license report, SBOM, and detect-secrets completed |
| `git diff --check` | 0 | no whitespace errors |

Supply-chain summary:

- `pip-audit`: 106 dependencies, 0 known vulnerabilities.
- `pip-licenses`: 103 package license entries.
- CycloneDX SBOM: 107 components.
- `detect-secrets`: 0 findings.

## 12. CI Status

Previous accepted baseline before this stage:

- Run id: `28535221021`
- Run URL: `https://github.com/bjdnm1377/AIOrganization/actions/runs/28535221021`
- Job id: `84594748216`
- Commit: `77c4a85b80ddcd71144af55ca30823bc2a06ff5d`
- Conclusion: `success`

New CI for this stage: not triggered yet.

Push attempts:

- `git push origin master`: failed, `Failed to connect to github.com port 443`
- `git ls-remote origin HEAD`: failed with the same Git endpoint connectivity
  error
- `Test-NetConnection github.com -Port 443`: latest result
  `TcpTestSucceeded=False`
- `curl https://api.github.com/repos/bjdnm1377/AIOrganization`: succeeded,
  confirming that GitHub API reachability is separate from the blocked Git/Web
  endpoint in this environment

The local commit is ready to push when `github.com:443` becomes reachable.

## 13. Reviewer Findings

Independent Reviewer findings and handling:

- P1: `local_cli` file scope could be widened by TaskSpec metadata. Fixed by
  forcing real CLI allowed files to `smoke/**`; added regression test.
- P1: auth/session/thread details could enter logs or API-visible metadata.
  Fixed by storing only coarse preflight and observed booleans; command logs no
  longer persist raw Codex JSONL or ids.
- P1: `codex doctor --json` preflight was not fail-closed. Fixed so timeout,
  nonzero exit, unparseable output, or readiness-not-confirmed return
  NOT_CONFIGURED before `codex exec`; added regression tests.
- P2: path redaction covered only the worktree. Fixed by redacting worktree,
  home, CODEX_HOME, AppData/LocalAppData, temp paths, JSON-escaped path forms,
  and generic Windows/POSIX absolute paths; added regression coverage.
- P2: real Codex command logs marked `network_requested=false`. Fixed by marking
  doctor and exec as network-requesting and adding `external_service_requested`
  / `external_service_used` metadata for real execution.
- P3: manual real Codex test could be collected by default pytest if the opt-in
  environment variable leaked in. Fixed by excluding `tests/manual` from default
  `testpaths`; CI also sets `AI_ORG_ENABLE_REAL_CODEX_SMOKE=false`.

All P1 and P2 findings were fixed before commit. P3 was also fixed.

## 14. Known Risks

- Real smoke uses the local user's existing Codex CLI auth session and may
  consume real Codex service capacity when manually enabled.
- Production Docker sandbox is not implemented.
- Codex MCP integration is not implemented.
- Worktree cleanup remains manual.
- This smoke test validates a minimal path only; it is not permission-system
  hardening for arbitrary code execution.

## 15. Not Completed

- Docker sandbox for untrusted code.
- Automatic merge, commit, or push of Codex output.
- Codex MCP adapter.
- OpenHands, Virtuoso, HFSS, MATLAB, Redis, Temporal, or Web frontend.

## 16. Next Stage Recommendation

Proceed to Docker sandbox and real code execution hardening only after this
stage's CI passes and the user accepts the controlled smoke result.

## 17. Git State

- Branch before stage commit: `master`
- Current pre-stage commit: `77c4a85b80ddcd71144af55ca30823bc2a06ff5d`
- Final local stage commit before blocked-report amend:
  `646cb71a1010b81bf5803e066785ec99fafe80fe`
- Final blocked-report commit: recorded in the final response because embedding
  a commit's own hash changes that hash.
- `git status --short`: pending final local status capture

## 18. User Acceptance Options

- Pass: enter Docker sandbox and real code execution hardening stage.
- Wait: keep real Codex smoke path implemented but do not proceed.
- Reject: continue fixing real Codex smoke test stage.
- Pause: stop for now.
- Adjust target: re-plan the next stage.
