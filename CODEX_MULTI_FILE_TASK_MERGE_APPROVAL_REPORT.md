# Controlled Multi-File Codex Task And Merge Candidate Report

Status: BLOCKED - CODEX CLI MULTI-FILE TASK TIMED OUT

## 1. Stage Goal

Resolve the real Codex multi-file task timeout without weakening worktree
isolation, file policy, approval policy, Docker sandbox checks, or the
main-worktree fingerprint guard. The stage remains limited to producing a
human-reviewable MergeCandidate artifact. It does not implement MergeService,
merge branches, push Codex output branches, open PRs, or deploy.

## 2. Current Status

Still blocked. The previous blocker was a main-worktree modification during a
real Codex multi-file run. The current implementation guarded the main worktree
successfully, but the real Codex CLI exec command timed out again after the
multi-file task was reduced from three files to two files.

The project must not enter the human-approved merge implementation stage.

## 3. Previous Failure

Earlier real multi-file validation produced a task-worktree MergeCandidate
artifact but also modified the main worktree. That result was rejected as an
isolation violation.

Implemented guard:

- Fingerprint covers `HEAD`, porcelain status with all untracked files, tracked
  diff, staged diff, and untracked file content hashes.
- If the main worktree changes during real Codex execution, the Worker result is
  forced to `FAILED`.
- `blocked_reason=MAIN_WORKTREE_MODIFIED`.
- `policy_violations` includes `main_worktree:modified`.
- Review Worker rejects.

## 4. Current Failure

The latest revalidation failed before review:

- Command:
  `$env:AI_ORG_ENABLE_REAL_CODEX_MULTI_FILE_TASK='true'; .\.venv\Scripts\python.exe -m pytest tests\manual\test_real_codex_multi_file_task.py -q`
- Result: `1 failed in 619.50s`.
- Failure: `Codex CLI multi-file task execution timed out.`
- Failure point: deterministic validation raised `ValidationFailure` for the
  failed Codex Worker result.
- Review Worker did not run in the manual workflow because deterministic
  validation blocked first.
- Unit coverage verifies Review Worker rejects timeout results with
  `codex:timeout`.

## 5. Timeout Root-Cause Analysis

- Actual Codex command:
  `codex --sandbox workspace-write --ask-for-approval on-request exec --json --cd <worktree> --color never -`.
- Exec timeout configuration: `600` seconds.
- Version timeout configuration: `15` seconds.
- Preflight timeout configuration: `30` seconds.
- `codex --version`: completed, `codex-cli 0.142.5`.
- `codex doctor --json`: completed, preflight passed.
- Codex emitted JSONL but did not finish.
- JSONL events observed: `9`.
- Error events observed: `4`.
- File-change events observed: `0`.
- Last JSONL event type: `item.completed`.
- Approval request observed: `false`.
- Network requested: `true` for doctor and exec.
- Privilege escalation observed: no.
- `danger-full-access`: not used.
- Main worktree modification: no.
- Task worktree diff: none.
- Docker sandbox did not run because Codex failed before sandbox validation.
- Diff collection and artifact writing completed and did not block.
- The evidence points to Codex CLI remote execution/transport stalling before
  making file changes, not a Docker sandbox or diff collector hang.
- Prompt length and task complexity were reduced, but timeout still occurred.
- Next likely recovery is a smaller real Codex task or split real Codex
  sub-tasks, not larger timeout or wider permissions.

## 6. Timeout Classification And Cleanup

- `blocked_reason`: `CODEX_CLI_TIMEOUT`.
- Command log `timeout_type`: `CODEX_CLI_TIMEOUT`.
- Elapsed time: `600328 ms`.
- Process killed: `true`.
- Process tree killed: `true`.
- Cleanup error: none recorded.
- No accepted MergeCandidate artifact was generated after timeout.

## 7. Current TaskSpec Summary

- `worker_type`: `codex`.
- `codex_mode`: `local_multi_file_task`.
- `codex_sandbox`: `workspace-write`.
- `codex_approval_policy`: `on-request`.
- `sandbox_test_profile`: `real_multi_file_task_merge_candidate`.
- `max_attempts`: `1`.
- Objective: add `MERGE_CANDIDATE_MANUAL_TASK_MARKER =
  'human-approval-only'` to the MergeCandidate module and add/update a unit test
  for that marker.
- Explicit exclusions: docs, config, workflows, dependencies, database, API,
  scripts, MergeService, long commands.

## 8. File Policy

Allowed files:

- `src/ai_org/adapters/codex/merge_candidate.py`
- `tests/unit/test_codex_merge_candidate.py`

Forbidden files include:

- `.git/**`
- `.github/**`
- `.env`
- `.env.*`
- `requirements-lock.txt`
- `requirements.in`
- `pyproject.toml`
- `alembic/**`
- `docs/**`
- `AGENTS.md`
- `README.md`
- `docker-compose.yml`
- `scripts/**`

Task metadata cannot widen the real multi-file allowed file set.

## 9. Worktree Evidence

- Logical worktree URI:
  `worktree://codex/task_e404a6e99ffe422599cfadba62acd47c/attempt-1`
- Branch:
  `ai-org/codex/98d67aab3398/adba62acd47c-1`
- Base commit:
  `b32f211bbad81ca20339814a67f32de125d765ea`
- Changed files: none.
- Diff summary: empty.
- MergeCandidate artifact URI: none generated.

## 10. Main Worktree Evidence

- Branch before run: `master`.
- HEAD before run: `b32f211bbad81ca20339814a67f32de125d765ea`.
- `origin/master` before report update:
  `c2056e449db9d28230ddc8100bdaf1764575f6b5`.
- `git status --short` before run: empty.
- Main worktree fingerprint before run:
  `a6fcb15b1f5d16f508fc5036ac3026393b3f1f838a72cff67205178b60e58785`.
- `git status --short` after run: empty.
- Main worktree fingerprint after run:
  `a6fcb15b1f5d16f508fc5036ac3026393b3f1f838a72cff67205178b60e58785`.
- Fingerprint consistent: yes.
- Main branch modified by Codex: no.
- Automatic merge: no.
- Automatic push: no.
- Automatic commit of Codex output branch: no.

## 11. Sandbox

Docker was available:

- Docker Server: `29.2.1`.

`DockerSandboxRunner` did not run during the latest manual test because Codex
timed out before producing a successful result. The fixed sandbox profile
remains in place and is covered by unit/default tests.

Sandbox policy summary:

- non-root user;
- network disabled;
- `--cap-drop ALL`;
- `no-new-privileges`;
- read-only root filesystem;
- explicit `/tmp` tmpfs;
- only task worktree mounted;
- no home, SSH, Git credential, cloud credential, `.env`, or Docker socket
  mounts;
- bounded CPU, memory, PID, timeout, stdout, and stderr.

## 12. Command Logs And Artifacts

Artifacts for the latest failed real run:

- `artifact://codex/task_e404a6e99ffe422599cfadba62acd47c/attempt-1/prompt.md`
- `artifact://codex/task_e404a6e99ffe422599cfadba62acd47c/attempt-1/command-log.json`
- `artifact://codex/task_e404a6e99ffe422599cfadba62acd47c/attempt-1/diff.patch`

Command log summary:

- `codex --version`: completed, exit `0`, duration `175 ms`.
- `codex doctor --json`: completed, exit `0`, preflight passed.
- `codex ... exec --json --cd <worktree> ...`: timeout after `600328 ms`,
  `timeout_type=CODEX_CLI_TIMEOUT`, `jsonl_event_count=9`,
  `jsonl_error_events=4`, `jsonl_file_change_events=0`,
  `approval_requested=false`, `process_killed=true`,
  `process_tree_killed=true`.

Prompt, command logs, and diff artifacts use logical worktree URIs or
`<worktree>` placeholders and do not expose the main repository absolute path.
No secret findings were detected by local `detect-secrets`.

## 13. Review, Audit, And API

- Manual workflow Review Worker decision: not reached because deterministic
  validation blocked the failed Codex result.
- Unit coverage Review Worker decision for timeout: rejected with
  `codex:timeout`.
- `merge_candidate.created` audit event: not created for the timed-out manual
  run.
- FastAPI query verification: default e2e tests passed locally; the manual
  real Codex test uses the application service and LangGraph workflow directly.

## 14. Local Validation

Validation before the implementation commit:

- `.\.venv\Scripts\python.exe -m ruff format --check .`: exit `0`.
- `.\.venv\Scripts\python.exe -m ruff check .`: exit `0`.
- `.\.venv\Scripts\python.exe -m mypy src tests`: exit `0`.
- `.\.venv\Scripts\python.exe -m pytest tests\unit\test_codex_worker.py tests\unit\test_codex_merge_candidate.py -q`:
  exit `0`, `49 passed`.
- `.\.venv\Scripts\python.exe -m pytest -q`: exit `0`,
  `108 passed, 2 skipped, 1 warning`.
- `.\scripts\supply_chain_checks.ps1 -Python .\.venv\Scripts\python.exe`:
  exit `0`.
- `git diff --check`: exit `0`.

Supply-chain results:

- `pip-audit`: no known vulnerabilities found.
- `detect-secrets`: 0 findings.
- License report and CycloneDX SBOM generated.

## 15. CI Evidence

Safety baseline commit `c2056e449db9d28230ddc8100bdaf1764575f6b5` was pushed
before this timeout-reduction work and passed GitHub Actions:

- Workflow: `Verification`.
- Run id: `28576035878`.
- URL: `https://github.com/bjdnm1377/AIOrganization/actions/runs/28576035878`.
- Conclusion: `success`.

The current timeout-reduction/report commits are recorded in the final response
after commit and CI completion. CI must continue to keep real Codex disabled.

## 16. Implemented In This Stage

- Reduced real multi-file allowed files from three files to two files.
- Moved `docs/**` into the forbidden file set for real multi-file Codex tasks.
- Shortened the manual real multi-file prompt.
- Removed documentation-file assertions from the multi-file sandbox test
  profile.
- Added explicit `CODEX_CLI_TIMEOUT` command-log diagnostics.
- Added elapsed-time, JSONL event, approval-observation, and process cleanup
  metadata for timeout logs.
- Added process-tree cleanup for subprocess timeout.
- Added Review Worker rejection for timeout results.
- Added tests for timeout classification, deterministic validation blocking,
  fingerprint post-check after timeout, no accepted MergeCandidate after
  timeout, two-file allowed scope, and process-tree cleanup.

## 17. Not Implemented

- No MergeService.
- No automatic merge.
- No automatic push of Codex output branches.
- No automatic commit of Codex output branches.
- No PR creation or deploy.
- No CI real Codex execution.
- No permission increase to `danger-full-access`.
- No wider allowed files.
- No API, database, migration, Redis, Temporal, OpenHands, Virtuoso, HFSS,
  MATLAB, or web frontend integration.

## 18. Known Risks

- Real Codex CLI can start a thread and emit JSONL while never completing the
  task on this host.
- The local Codex app-server process remains a shared host runtime outside the
  repository process tree.
- The current manual task may need to be reduced further to one real Codex
  sub-task, or split into sequential real Codex child tasks.
- Worktree cleanup remains manual.
- Docker sandboxing remains a fixed-command foundation, not production
  arbitrary-code execution.

## 19. Next Recommended Step

Do not enter merge implementation. Keep status as waiting/blocked and either:

- reduce the real Codex task to one file plus a separate real test-file task; or
- introduce an explicit two-step real Codex sub-task flow where each Codex run
  touches one allowed file and is independently reviewed; or
- investigate Codex CLI transport/runtime behavior outside the AI Organization
  workflow before another full validation attempt.

Do not solve this by increasing timeout indefinitely, increasing permissions,
running in the main worktree, or relaxing file policy.

## 20. Current Git State

- Current branch: `master`.
- Timeout-reduction implementation commit before report update:
  `b32f211bbad81ca20339814a67f32de125d765ea`.
- Final report commit: recorded in the final response.
- `origin/master` before report update:
  `c2056e449db9d28230ddc8100bdaf1764575f6b5`.
- `git status --short` after report edit: report file modified only until the
  final report commit is created.

## 21. User Acceptance Options

- 通过：进入人工审批后受控 merge 实现阶段。
- 等待：真实 multi-file task 仍被 timeout 或隔离边界阻塞。
- 驳回：继续修复受控多文件代码任务阶段。
- 暂停：暂不继续。
- 调整目标：重新规划下一阶段。
