# Controlled Multi-File Codex Task And Merge Candidate Report

Status: BLOCKED - CODEX MULTI-FILE TASK FAILED

## 1. Stage Goal

Verify that a real Codex Worker can complete a controlled multi-file task inside
a task-scoped worktree and produce a human-reviewable MergeCandidate summary
without automatic merge, push, PR creation, deploy, or main-branch mutation.

## 2. Current Status

Blocked. The real Codex multi-file task produced the expected task-worktree
MergeCandidate artifact, but the real Codex process also modified files in the
main worktree outside the allowed task worktree. That violates the isolation
requirement, so this stage is not accepted and the project must not enter the
human-approved merge implementation stage yet.

## 3. Codex Detection

- `codex --version`: `codex-cli 0.135.0`.
- `codex doctor --json`: authentication configured; overall warning because
  WebSocket reachability timed out, HTTPS fallback may still work.
- Docker: Docker Desktop 29.2.1; daemon was restarted locally and default
  tests later passed.

## 4. Opt-In

- Default CI and default tests keep real Codex disabled.
- `AI_ORG_ENABLE_REAL_CODEX_MULTI_FILE_TASK=true` was used only for the manual
  local real Codex test.
- `.github/workflows/verification.yml` sets
  `AI_ORG_ENABLE_REAL_CODEX_MULTI_FILE_TASK=false`.

## 5. Real Task Evidence

Manual test command:

```powershell
$env:AI_ORG_ENABLE_REAL_CODEX_MULTI_FILE_TASK='true'
.\.venv\Scripts\python.exe -m pytest tests\manual\test_real_codex_multi_file_task.py -q
```

Observed result: failed. The workflow path reached `ProjectStatus.COMPLETED`
for the task-worktree result in one run, but the test assertion detected that
the main worktree changed. The test therefore failed.

Task-worktree artifact:

- `artifact://codex/task_57e08a8cef6e4e75ac6ab961030a622e/attempt-1/merge-candidate.json`
- `changed_files`: `docs/MERGE_APPROVAL.md`,
  `src/ai_org/adapters/codex/merge_candidate.py`,
  `tests/unit/test_codex_merge_candidate.py`
- `tests_passed`: `true`
- `merge_performed`: `false`
- `auto_merge`: `false`
- `auto_push`: `false`
- `human_approval_required`: `true`

Failure reason:

- Main worktree changed during the real Codex run.
- Real Codex also generated broader MergeService/database/API files in the main
  repository; these were removed as unapproved out-of-scope changes.

## 6. Implemented Fix

Added a fail-closed main-worktree guard:

- `WorktreeService.status_fingerprint()` computes a fingerprint from tracked
  diff, staged diff, and untracked file content hashes.
- `CodexWorker` captures the fingerprint before and after local real Codex
  execution.
- If the main worktree fingerprint changes, the result is forced to FAILED with
  `MAIN_WORKTREE_MODIFIED`.
- The result metadata includes `main_worktree_modified=true`.
- The policy violations include `main_worktree:modified`.
- Review Worker rejects the result.

This fixes the reviewer finding that comparing only `git status --short` was
insufficient when a file was already dirty before Codex mutated it again.

## 7. Files Changed

- `src/ai_org/adapters/codex/worktree.py`
- `src/ai_org/adapters/codex/worker.py`
- `tests/unit/test_codex_worker.py`
- `docs/CODEX_WORKER.md`
- `docs/CODING_WORKER_SECURITY.md`
- `docs/WORKTREE_ISOLATION.md`
- `docs/TESTING.md`
- `docs/THREAT_MODEL.md`
- `CODEX_MULTI_FILE_TASK_MERGE_APPROVAL_REPORT.md`

No MergeService, database table, API endpoint, auto-merge, auto-push, PR, or
deploy implementation is included in the accepted diff.

## 8. Validation Commands

- `python -m ruff format --check .`: exit 0.
- `python -m ruff check .`: exit 0.
- `python -m mypy src tests`: exit 0.
- `python -m pytest tests/unit/test_codex_worker.py tests/unit/test_worktree_service.py -q`:
  exit 0, 42 passed, 1 skipped.
- `python -m pytest -q`: exit 0, 97 passed, 1 skipped, 1 warning.
- `.\scripts\supply_chain_checks.ps1 -Python .\.venv\Scripts\python.exe`:
  exit 0.
- `git diff --check`: exit 0.

Supply-chain results:

- `pip-audit`: no known vulnerabilities found; local package
  `ai-organization` skipped because it is not on PyPI.
- `pip-licenses`: generated `reports/license-report.json`.
- CycloneDX SBOM: generated `reports/sbom.json`.
- `detect-secrets`: 0 findings.

## 9. Reviewer Findings

Independent reviewer: Zeno.

High severity findings:

- Main worktree guard used only `git status --short`; fixed with fingerprint
  including diff and untracked content hashes.
- Missing stage report; fixed by this report.

Medium severity findings:

- Documentation wording implied a stronger guard than implemented; fixed by
  implementing the stronger fingerprint guard and updating docs.
- Unit test only covered new-file side effect; fixed with a dirty-file mutation
  test where `git status --short` stays unchanged but content changes.

Low severity findings:

- Dirty working tree before final commit; expected while report and fixes were
  being prepared.

## 10. Risks

- The local real Codex process demonstrated that `--cd <worktree>` plus
  `workspace-write` is not sufficient isolation on this host.
- Real Codex can still consume external service capacity during manual tests.
- The manual multi-file test must remain blocked until the execution boundary
  is strengthened, likely by running real Codex in a separate disposable clone
  or a stricter process/container boundary with host write protection.

## 11. Not Completed

- Real Codex multi-file stage is not verified complete.
- No human-approved merge implementation was started.
- No automatic merge, push, PR, deploy, or worktree deletion was implemented.

## 12. Next Recommended Step

Do not enter the human-approved merge implementation stage yet. First add a
stronger real-Codex execution boundary:

- run real Codex only in a disposable clone or isolated working directory;
- deny write access to the main repository during real Codex execution;
- re-run the multi-file task and require main worktree fingerprint stability;
- only then allow this stage to move from blocked to verified.

## 13. Git State

- Branch: `master`.
- Base commit before this report/fix commit: `77f8ccbf3d1dbfc7c9695a5fe8ea15daeca1025d`.
- Final commit hash: recorded in the final user response after commit creation.
- `git status --short` before commit: expected modified report/fix files only.

## 14. User Acceptance Options

- 等待：真实 multi-file task 已阻塞，等待隔离边界修复。
- 驳回：继续修复受控多文件代码任务阶段。
- 暂停：暂不继续。
- 调整目标：重新规划下一阶段。
