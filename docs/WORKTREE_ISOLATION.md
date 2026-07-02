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
- No automatic merge is performed.
- No automatic push is performed.
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

- `docs/MERGE_APPROVAL.md`
- `src/ai_org/adapters/codex/merge_candidate.py`
- `tests/unit/test_codex_merge_candidate.py`

The policy forbids repository control files, workflow files, dependency files,
migrations, scripts, `AGENTS.md`, `README.md`, `docker-compose.yml`, and
`.env*`. The task runs in a dedicated worktree. The resulting
MergeCandidate artifact is a review surface only; it is not committed, merged,
pushed, or deployed automatically.

## Cleanup

`cleanup_worktree()` can remove a known worktree and branch. Automatic retention
or abandoned-worktree cleanup is not implemented yet; this is recorded as a known
operational risk for later stages.
