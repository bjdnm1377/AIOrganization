# Worktree Isolation

## Implemented

`WorktreeService` creates one Git branch/worktree per Codex task attempt under
`.ai_org_worktrees/`. The branch name includes project and task identifiers, and
the service records the base commit.

Safety controls:

- Worktree root must resolve inside the repository.
- Task and project ids are sanitized before they become path or branch parts.
- Resolved worktree paths are checked so path traversal cannot escape the
  worktree root.
- Symlink roots that resolve outside the repository are rejected.
- The main working tree is not modified by Mock/DryRun Codex task file changes.
- The main working tree is not modified by the manual real Codex CLI smoke test;
  Codex runs in the task worktree with `--cd <worktree>`.
- The main working tree is not modified by the manual real Codex small code
  task; changed files are collected from the task worktree and reviewed without
  automatic merge.
- The main working tree is not modified by the manual real Codex multi-file
  task; changed files are collected from the task worktree and represented as a
  pending MergeCandidate summary without automatic merge.
- The manual real Codex stepwise multi-file task also runs only in the task
  worktree. It splits one logical multi-file task into multiple single-file
  Codex CLI invocations and re-checks the main-worktree fingerprint after each
  step.
- No automatic merge is performed.
- No automatic push is performed.
- Local real Codex Worker execution compares a main-worktree fingerprint before
  and after the run. The fingerprint includes `HEAD`, `git status
  --porcelain=v1 --untracked-files=all`, tracked diffs, staged diffs, and
  untracked file content hashes. If the main worktree changes, the result is
  rejected as `MAIN_WORKTREE_MODIFIED`.
- Task worktree diffs are collected from the task worktree only. Changed
  symlinks that resolve outside the task worktree are treated as forbidden file
  violations.
- API-visible metadata uses `worktree://codex/{task_id}/attempt-{n}` logical
  URIs instead of local absolute paths.
- Docker sandbox integration mounts only the task worktree at `/workspace`; it
  does not mount the main repository, user home, SSH agent, Git credentials,
  cloud credentials, `.env` files, or the Docker socket.

## Real Codex Smoke Scope

For `codex_mode="local_cli"`, the intended smoke task creates only:

- `smoke/codex_worker_smoke.txt`

The smoke-stage policy forbids changes to source, tests, docs, dependency
files, workflow files, migrations, `AGENTS.md`, `README.md`, `.env*`, and
`.git/**`. Any forbidden change is reported by `DiffCollector` and rejected by
the independent Review Worker.

## Real Codex Small Code Task Scope

For `codex_mode="local_code_task"`, the intended task may create or update only:

- `src/ai_org/adapters/codex/smoke_helpers.py`
- `tests/unit/test_codex_smoke_helpers.py`

The policy forbids repository control files, workflow files, dependency files,
migrations, docs, `AGENTS.md`, `README.md`, `docker-compose.yml`, `scripts/**`,
and `.env*`. The task runs in a dedicated worktree and is not committed, merged,
or pushed automatically.

## Real Codex Multi-File Merge Candidate Scope

For `codex_mode="local_multi_file_task"`, the intended task may create or update
only:

- `src/ai_org/adapters/codex/merge_candidate.py`
- `tests/unit/test_codex_merge_candidate.py`

The policy forbids documentation files, repository control files, workflow
files, dependency files, migrations, scripts, `AGENTS.md`, `README.md`,
`docker-compose.yml`, and `.env*`. The task runs in a dedicated worktree. The
resulting
MergeCandidate artifact is a review surface only; it is not committed, merged,
pushed, or deployed automatically.

A previous real Codex multi-file validation run produced the expected
MergeCandidate worktree artifact but also modified the main worktree. That run
failed the stage. The current guard is fail-closed: any tracked, staged, or
untracked main-worktree content change during local real Codex execution forces
the task result to `FAILED`, adds `main_worktree:modified`, prevents a passing
MergeCandidate artifact, and causes independent review rejection.

A later revalidation run kept the main-worktree fingerprint stable but timed
out during Codex CLI exec before producing a task-worktree diff. Timeout is now
reported as `CODEX_CLI_TIMEOUT` with diagnostic command-log metadata and
process-tree cleanup status. It remains a blocked result and cannot advance to
merge approval.

## Real Codex Stepwise Multi-File Merge Candidate Scope

For `codex_mode="local_stepwise_multi_file_task"`, the logical task still has
the same two-file final scope:

- `src/ai_org/adapters/codex/merge_candidate.py`
- `tests/unit/test_codex_merge_candidate.py`

The worker executes that logical task as two real Codex steps. Step 1 may only
change the source file and Step 2 may only change the test file. Each step has
its own allowed-file policy, forbidden-file policy, timeout diagnostics, main
worktree fingerprint before/after values, and task-worktree dirty-file
fingerprint comparison. A step that modifies any other file fails the logical
task, prevents an accepted MergeCandidate, and is rejected by review. A step
timeout is classified as `CODEX_STEP_TIMEOUT` and also prevents a passing
MergeCandidate.

The stepwise path does not merge, commit, push, open PRs, delete worktrees, or
modify the main branch. It produces only a pending MergeCandidate artifact after
all steps and the fixed sandbox validation pass.

## Cleanup

`cleanup_worktree()` can remove a known worktree and branch. Automatic retention
or abandoned-worktree cleanup is not implemented yet; this is recorded as a known
operational risk for later stages.
