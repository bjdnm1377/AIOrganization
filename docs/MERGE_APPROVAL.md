# Merge Approval

## Current Status

Merge approval is not an automatic merge feature. The implemented capability is
a read-only, side-effect-free MergeCandidate summary that can be reviewed by a
human before a later merge implementation exists.

The controlled multi-file Codex validation previously failed because real Codex
modified the main worktree while also producing a task-worktree
MergeCandidate. That output is not accepted. Current validation requires the
main worktree fingerprint to remain identical before and after real Codex
execution; otherwise the result is `FAILED` with
`MAIN_WORKTREE_MODIFIED` and no passing merge candidate is produced.

A later revalidation attempt kept the main worktree fingerprint identical but
the Codex CLI exec command timed out before producing a task-worktree diff. That
result is also not accepted. Timeout is classified as `CODEX_CLI_TIMEOUT`, does
not create an accepted MergeCandidate, and must be resolved before any merge
approval implementation begins.

The current recovery path does not increase timeout indefinitely or widen
permissions. Instead, `codex_mode="local_stepwise_multi_file_task"` splits one
logical multi-file task into fixed single-file Codex steps. Each step has one
allowed file, an independent forbidden-file policy, a main-worktree fingerprint
before/after check, task-worktree dirty-file comparison, timeout diagnostics,
and process cleanup evidence. A failed step prevents an accepted
MergeCandidate. This is still merge-candidate generation only, not merge
approval execution.

## MergeCandidate Summary

`build_merge_candidate_summary()` shapes structured data for a candidate:

- changed files are sorted and local absolute paths are redacted;
- `review_decision` records the current review state;
- `tests_passed` records whether deterministic checks passed;
- `merge_performed` is always `False`;
- `auto_merge` is always `False`;
- `auto_push` is always `False`;
- `human_approval_required` is always `True`;
- `requires_human_merge_approval` is always `True`;
- `approval_state` is `waiting_merge_approval`.

The function does not read files, write files, execute shell commands, call the
network, read environment variables, merge branches, push branches, delete
worktrees, or deploy.

## Workflow Boundary

For `codex_mode="local_multi_file_task"`, `CodexWorker` may create a
`merge-candidate` artifact after the task worktree diff is collected. The real
Codex task is currently limited to `src/ai_org/adapters/codex/merge_candidate.py`
and `tests/unit/test_codex_merge_candidate.py`; documentation updates stay
outside the real Codex task. The independent Review Worker must accept the
Coding Worker result before the application writes a `merge_candidate.created`
audit event.

The main branch remains unchanged. The task worktree remains a manual review
surface. Later stages may add a `MergeService`, but it must require explicit
human approval, re-check policy, re-check tests, and refuse high-risk files
without a separate approval path.

For the stepwise path, the final MergeCandidate may be created only after both
single-file steps and the fixed sandbox test pass. It records logical worktree
URI, branch name, base commit, head state, `requires_human_merge_approval=True`,
`auto_merge=False`, and `auto_push=False`.

This document does not authorize merge implementation, automatic merge,
automatic push, or automatic PR creation. Until a later human-approved stage,
MergeCandidate artifacts are evidence for review only.

## High-Risk Files

The current multi-file task policy allows only:

- `src/ai_org/adapters/codex/merge_candidate.py`
- `tests/unit/test_codex_merge_candidate.py`

Documentation files, repository control files, dependency files, migrations, CI
workflows, scripts, environment files, credentials, `AGENTS.md`, `README.md`,
and production config are outside this task scope. If any such file changes,
the result is rejected before merge approval can be considered.
