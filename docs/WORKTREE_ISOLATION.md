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
- No automatic merge is performed.
- API-visible metadata uses `worktree://codex/{task_id}/attempt-{n}` logical
  URIs instead of local absolute paths.

## Real Codex Smoke Scope

For `codex_mode="local_cli"`, the intended smoke task creates only:

- `smoke/codex_worker_smoke.txt`

The smoke-stage policy forbids changes to source, tests, docs, dependency
files, workflow files, migrations, `AGENTS.md`, `README.md`, `.env*`, and
`.git/**`. Any forbidden change is reported by `DiffCollector` and rejected by
the independent Review Worker.

## Cleanup

`cleanup_worktree()` can remove a known worktree and branch. Automatic retention
or abandoned-worktree cleanup is not implemented yet; this is recorded as a known
operational risk for later stages.
