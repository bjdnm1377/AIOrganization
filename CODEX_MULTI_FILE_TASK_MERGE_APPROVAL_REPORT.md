# Controlled Multi-File Codex Task And Merge Candidate Report

Status: BLOCKED - CODEX STEPWISE MULTI-FILE TASK TIMED OUT

## 1. Stage Goal

Prove that one logical multi-file Coding Task can be orchestrated as multiple
controlled single-file Codex CLI steps. Each step must run in the task
worktree, have one allowed file, retain forbidden-file boundaries, record
timeout diagnostics, preserve the main-worktree fingerprint, and stop before
any merge implementation. A passing result would generate only a pending
MergeCandidate artifact for human review.

This stage does not implement MergeService, perform merge, push a Codex output
branch, create a PR, delete worktrees, or deploy.

## 2. Current Status

The implementation for stepwise orchestration exists locally, but real manual
validation is still blocked. The latest real run timed out during Step 1 before
any file changes were observed.

The project must not enter the human-approved merge implementation stage.

Follow-on CLI diagnostics have now reduced the problem below the multi-file
orchestration layer. Version and doctor checks completed, read-only stdin and
argument exec prompts completed near their timeout bounds with transport-stall
signals, and the minimal workspace-write single-file create diagnostic timed
out after 180 seconds with no file-change events. The current diagnostic status
is recorded in `CODEX_CLI_DIAGNOSTIC_REPORT.md` as
`BLOCKED - CODEX CLI DIAGNOSTIC TIMEOUT`.

## 3. Previous Failure

Earlier real single-call multi-file validation produced a task-worktree
MergeCandidate artifact but also modified the main worktree. That result was
rejected as an isolation violation.

A later single-call multi-file revalidation kept the main-worktree fingerprint
stable but timed out after 600 seconds with no task-worktree diff and no
MergeCandidate artifact. That result remains blocked as
`CODEX_CLI_TIMEOUT`.

## 4. Current Strategy Change

The new strategy does not ask one Codex CLI invocation to complete multiple
files. `CodexWorker` now supports `codex_mode="local_stepwise_multi_file_task"`
and requires explicit opt-in:

- `AI_ORG_ENABLE_REAL_CODEX_STEPWISE_MULTI_FILE_TASK=true`

The logical task is split into fixed single-file steps:

- Step 1: source-file implementation.
- Step 2: unit-test implementation.

Each step uses a short prompt, task-worktree cwd/`--cd`, independent
allowed/forbidden files, per-step main-worktree fingerprint checks,
task-worktree dirty-file fingerprint checks, command-log sanitization, timeout
classification, and process-tree cleanup metadata.

## 5. Stepwise Orchestration Design

- Logical TaskSpec: implement MergeCandidate summary behavior and tests.
- StepSpec count: 2.
- Step execution: one real Codex CLI call per step.
- Step prompt: no main repository absolute path, no token, no API key, no auth
  path, no user directory, no GitHub credential.
- Step failure behavior: stop later steps, mark the logical task FAILED, do not
  generate an accepted MergeCandidate, and require Review Worker rejection.
- Success behavior: aggregate changed files, run fixed sandbox test, write a
  pending MergeCandidate artifact, require independent Review Worker
  acceptance, and still do not merge or push.

## 6. Step Policies

Step 1 allowed file:

- `src/ai_org/adapters/codex/merge_candidate.py`

Step 1 extra forbidden files:

- `tests/**`

Step 2 allowed file:

- `tests/unit/test_codex_merge_candidate.py`

Step 2 extra forbidden files:

- `src/**`

Both steps also inherit forbidden patterns for `.git/**`, `.github/**`,
`.env*`, dependency files, `pyproject.toml`, migrations, docs, scripts,
`AGENTS.md`, `README.md`, `docker-compose.yml`, and credential-bearing files.

## 7. Timeout Configuration

- Codex version timeout: `15` seconds.
- Codex doctor/preflight timeout: `30` seconds.
- Step exec timeout in the latest manual run: `240` seconds.
- Logical stepwise total timeout: `540` seconds.
- Docker sandbox command timeout: controlled by `DockerSandboxRunner` resource
  limits.
- Diff collection uses the existing bounded git diff collection path.

## 8. Latest Real Step Results

Manual command:

```powershell
$env:AI_ORG_ENABLE_REAL_CODEX_STEPWISE_MULTI_FILE_TASK='true'
.\.venv\Scripts\python.exe -m pytest tests\manual\test_real_codex_stepwise_multi_file_task.py -q
```

Result:

- Exit code: `1`.
- Pytest result: `1 failed in 260.02s`.
- Failure: `ValidationFailure: Codex CLI stepwise multi-file task execution
  timed out.`
- Failed step: Step 1.
- Step 2: not executed.
- MergeCandidate artifact: not generated.

Step 1 command logs:

- `codex --version`: completed, exit `0`, `codex-cli 0.142.5`.
- `codex doctor --json`: completed, exit `0`, preflight passed.
- `codex ... exec --json --cd <worktree> ...`: timed out after `240275 ms`.
- Timeout type: `CODEX_STEP_TIMEOUT`.
- JSONL events: `9`.
- JSONL error events: `4`.
- JSONL file-change events: `0`.
- Last JSONL event type: `item.started`.
- Approval requested: `false`.
- Network requested: `true`.
- Process killed: `true`.
- Process tree killed: `true`.
- Cleanup error: none recorded.

## 9. Codex CLI And Opt-In

- Codex CLI version: `codex-cli 0.142.5`.
- Stepwise opt-in: enabled only for the manual command above.
- CI opt-in: `AI_ORG_ENABLE_REAL_CODEX_STEPWISE_MULTI_FILE_TASK=false`.
- Default tests: do not call real Codex.
- Real API keys: not requested and not used.

## 10. TaskSpec Summary

- `worker_type`: `codex`.
- `codex_mode`: `local_stepwise_multi_file_task`.
- `codex_sandbox`: `workspace-write`.
- `codex_approval_policy`: `on-request`.
- `sandbox_test_profile`: `real_stepwise_multi_file_task_merge_candidate`.
- `max_attempts`: `1`.
- Objective: run the controlled stepwise MergeCandidate task without
  MergeService, merge, commit, push, docs, config, workflow, or dependency
  changes.

## 11. Changed Files And Diff Summary

Task worktree:

- Branch: `ai-org/codex/3a9e9f85b169/bf450343e65b-1`.
- Base/head state: `af2bc44f66e226f8819c6a8e834f45fe6955f315`.
- `git status --short`: empty.
- Changed files: none.
- Diff artifact length: `0`.
- Diff summary: empty.
- Secret patterns in diff: none.

Because Step 1 timed out before file changes, Step 2 did not run and there is
no merged logical changed-file set.

## 12. Main Worktree Fingerprint Evidence

Before latest real stepwise run:

- Branch: `master`.
- HEAD: `af2bc44f66e226f8819c6a8e834f45fe6955f315`.
- `origin/master`: `c60249214f9340c5095640880cd042d5645a5f58`.
- `git status --short`: empty.
- Main worktree fingerprint:
  `8bc49eb51f4af2dbab34b739e8cdea2e872210b3bf0b52359fcfc61602801fba`.

After latest real stepwise run:

- `git status --short`: empty.
- Main worktree fingerprint:
  `8bc49eb51f4af2dbab34b739e8cdea2e872210b3bf0b52359fcfc61602801fba`.
- Fingerprint consistent: yes.
- Main branch modified by Codex: no.
- Automatic merge: no.
- Automatic push: no.
- Automatic commit of Codex output branch: no.

## 13. Artifacts

Latest failed real run artifacts:

- `artifact://codex/task_1fe326684f374ff9a323bf450343e65b/attempt-1/prompt.md`
- `artifact://codex/task_1fe326684f374ff9a323bf450343e65b/attempt-1/step-1-prompt.md`
- `artifact://codex/task_1fe326684f374ff9a323bf450343e65b/attempt-1/step-2-prompt.md`
- `artifact://codex/task_1fe326684f374ff9a323bf450343e65b/attempt-1/command-log.json`
- `artifact://codex/task_1fe326684f374ff9a323bf450343e65b/attempt-1/diff.patch`

MergeCandidate artifact URI:

- none generated.

Prompt, command-log, and diff artifacts use logical worktree URIs or
`<worktree>` placeholders and do not expose the main repository absolute path.

## 14. Sandbox

Docker was available for the manual stepwise run:

- Docker Server: `29.2.1`.

`DockerSandboxRunner` did not execute the fixed pytest validation because Step 1
timed out before a successful Codex result.

Sandbox policy remains:

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

## 15. MergeCandidate Boundary

No MergeCandidate was generated for the timed-out run.

The implemented MergeCandidate summary path still records:

- `merge_performed=False`;
- `auto_merge=False`;
- `auto_push=False`;
- `human_approval_required=True`;
- `requires_human_merge_approval=True`;
- `approval_state="waiting_merge_approval"`;
- logical task worktree URI;
- branch name;
- base commit;
- head state.

This is artifact generation only. It is not MergeService and it does not
perform branch operations.

## 16. Review Worker Decision

Manual workflow Review Worker step was not reached because deterministic
validation blocks FAILED worker results first.

Independent Review Worker was invoked against an equivalent
`CODEX_STEP_TIMEOUT` Coding Worker result:

- Decision: `REJECTED`.
- Defects: `codex:timeout`.

Unit tests also verify timeout rejection and no accepted MergeCandidate after
step timeout.

## 17. Audit Events

Latest real stepwise run:

- `coding_worker.completed`: worker result persisted before deterministic
  validation failed.
- `merge_candidate.created`: not created.

The successful audit-event path remains covered by default tests with Mock/Fake
Codex behavior only.

## 18. Local Validation

Before the real manual stepwise run, local validation on implementation commit
`af2bc44f66e226f8819c6a8e834f45fe6955f315`:

- `.\.venv\Scripts\python.exe -m ruff format --check .`: exit `0`.
- `.\.venv\Scripts\python.exe -m ruff check .`: exit `0`.
- `.\.venv\Scripts\python.exe -m mypy src tests`: exit `0`.
- `.\.venv\Scripts\python.exe -m pytest tests\unit\test_codex_merge_candidate.py tests\unit\test_ci_real_codex_disabled.py tests\unit\test_codex_worker.py -q`:
  exit `0`, `61 passed`.
- `.\.venv\Scripts\python.exe -m pytest -q`: exit `0`,
  `119 passed, 2 skipped, 1 warning`.

The first full pytest attempt failed only because Docker Desktop was not
running. Docker Desktop was then started, `docker info` confirmed Server
`29.2.1`, and the full pytest suite passed.

- `.\scripts\supply_chain_checks.ps1 -Python .\.venv\Scripts\python.exe`:
  exit `0`; `pip-audit` reported no known vulnerabilities; `detect-secrets`
  reported `0` findings; license report and CycloneDX SBOM were generated.
- `git diff --check`: exit `0`.

## 19. CI Evidence

The blocked stepwise implementation and report commits were pushed to preserve
the safety gates and timeout diagnostics, but that CI result does not turn the
real stepwise manual validation into a pass.

- Workflow: `Verification`.
- Run id: `28655649683`.
- Run URL: `https://github.com/bjdnm1377/AIOrganization/actions/runs/28655649683`.
- Commit: `fbba2bfceee6acb21483ecb0eff0af34b5b0cf51`.
- Conclusion: success.

CI did not call real Codex. Real stepwise validation remains blocked and no
accepted MergeCandidate exists.

## 20. Implemented Locally In This Stage

- Added `local_stepwise_multi_file_task` mode.
- Added explicit opt-in
  `AI_ORG_ENABLE_REAL_CODEX_STEPWISE_MULTI_FILE_TASK`.
- Added fixed Step 1 and Step 2 prompts with no main-repo absolute paths.
- Added per-step single-file policies.
- Added per-step task-worktree dirty-file fingerprint comparison.
- Added per-step main-worktree fingerprint before/after recording.
- Added `CODEX_STEP_TIMEOUT` normalization.
- Added failed-step metadata and timeout diagnostics.
- Added fixed sandbox profile
  `real_stepwise_multi_file_task_merge_candidate`.
- Added MergeCandidate metadata for logical worktree URI, branch, base commit,
  head state, and `requires_human_merge_approval=True`.
- Added Review Worker rejection for `CODEX_STEP_TIMEOUT`.
- Added CI env guard keeping the new real Codex path disabled.
- Added unit and manual tests for the stepwise path.
- Updated isolation, security, testing, merge-approval, threat-model, real-code,
  worker, and roadmap documentation.

## 21. Test Coverage Added Or Updated

Default tests now cover:

- logical multi-file task split into two single-file steps;
- independent step allowed files;
- Step 1 cannot modify the test file;
- Step 2 cannot modify the source file;
- forbidden file modification fails the logical task;
- step timeout fails the logical task;
- timeout does not generate a MergeCandidate;
- main-worktree fingerprint change fails the logical task;
- prompts do not contain the main repository absolute path;
- command logs do not expose token-like output;
- Codex cwd/`--cd` is the task worktree;
- process-tree cleanup metadata after timeout;
- all steps success produces a pending MergeCandidate artifact;
- MergeCandidate artifact does not expose local absolute paths;
- MergeCandidate marks human merge approval required;
- no automatic merge;
- no automatic push;
- CI does not call real Codex;
- Docker sandbox, PostgreSQL checkpoint, supply-chain, secret scan, and SBOM
  checks remain part of the verification plan.

## 22. Not Implemented

- No MergeService.
- No automatic merge.
- No automatic push.
- No automatic commit of Codex output branches.
- No PR creation or deploy.
- No CI real Codex execution.
- No permission increase to `danger-full-access`.
- No wider allowed files.
- No API, database, migration, Redis, Temporal, OpenHands, Virtuoso, HFSS,
  MATLAB, or web frontend integration.

## 23. Known Risks

- Real Codex CLI can start a thread and emit JSONL while never completing even
  a single-file step on this host.
- The local Codex app-server process remains a shared host runtime outside the
  repository process tree.
- Stepwise orchestration reduces task complexity but does not by itself fix a
  Codex CLI transport/runtime stall.
- Worktree cleanup remains manual.
- Docker sandboxing remains a fixed-command foundation, not production
  arbitrary-code execution.

## 24. Unfinished Content

- Real stepwise multi-file manual validation is not passing.
- No accepted real stepwise MergeCandidate has been generated.
- Follow-on real CLI diagnostics are also blocked by a single-file create
  timeout.
- Independent Reviewer for the current diagnostic stage is pending until the
  diagnostic report commit has passed CI.
- MergeService remains intentionally unimplemented.

## 25. Next Stage Recommendation

Do not enter the human-approved merge implementation stage.

Recommended next work is to debug or further reduce the real Codex single-file
step execution path. Possible options:

- inspect local Codex CLI/app-server transport behavior outside the workflow;
- restart or repair the local Codex app-server path;
- re-check Codex auth and consider upgrading or downgrading the CLI;
- repeat the same diagnostic from WSL or Linux if the Windows host remains
  unstable;
- keep timeout finite and preserve `CODEX_STEP_TIMEOUT` diagnostics.

Do not solve this by increasing permissions, running in the main worktree,
relaxing file policy, disabling fingerprint checks, or treating the timeout as
success.

## 26. Current Git State

- Current branch: `master`.
- Current local commit hash before diagnostic report update:
  `c9ea4becfffdb22866fc92f1abcf4933f795637a`.
- `origin/master` commit hash:
  `fbba2bfceee6acb21483ecb0eff0af34b5b0cf51`.
- `git status --short` before diagnostic report update: empty.
- Local master is ahead of origin after the diagnostic scaffold commit.
- No Codex output branch was pushed.

## 27. User Acceptance Options

- 通过：进入人工审批后受控 merge 实现阶段；
- 等待：真实 stepwise 或 diagnostic Codex 执行仍被 timeout 或隔离边界阻塞；
- 驳回：继续修复受控多文件代码任务阶段；
- 暂停：暂不继续；
- 调整目标：重新规划下一阶段。
