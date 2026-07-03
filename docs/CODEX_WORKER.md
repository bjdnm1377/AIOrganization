# Codex Worker

## Implemented

`CodexWorker` is registered under `worker_type="codex"` through the existing
WorkerRegistry. It accepts a normal `WorkerRequest`, creates a task-scoped Git
worktree, renders a constrained coding prompt, delegates to a `CodexClient`, and
returns a structured `AgentResult`.

Implemented clients:

- `MockCodexClient`: deterministic local file change simulation for tests.
- `DryRunCodexClient`: no-op dry run that records no real Codex process.
- `LocalCodexCliClient`: optional local real Codex CLI smoke path. It returns
  NOT_CONFIGURED unless the matching explicit opt-in is set.

No default code path requires an OpenAI key, Codex login, paid service, or real
shell execution. CI uses only Mock/DryRun and NOT_CONFIGURED behavior.

## Optional Sandbox Hook

`CodexWorker` can receive a `SandboxRunner` implementation. It only invokes the
sandbox when task metadata requests a fixed profile:

- `sandbox_smoke=True` runs a fixed health check and records `sandbox.health`.
- `sandbox_test_profile="real_code_task_smoke"` runs a fixed Python validation
  command after a small real code task and records `sandbox.test`.
- `sandbox_test_profile="real_multi_file_task_merge_candidate"` runs a fixed
  Python validation command after a controlled multi-file task and records
  `sandbox.test`.
- `sandbox_test_profile="real_stepwise_multi_file_task_merge_candidate"` runs
  `python -m pytest tests/unit/test_codex_merge_candidate.py -q` after the
  controlled stepwise multi-file task and records `sandbox.test`.

These hooks verify integration with the sandbox foundation without executing
user-provided commands or calling real Codex inside Docker.

## Local Real Codex CLI Smoke Path

The real path is deliberately narrow:

- `LocalCodexCliClient` first checks explicit opt-in.
- It detects the installed CLI with `codex --version`.
- It runs `codex doctor --json` as a fail-closed preflight and records only
  coarse readiness, not auth details; raw doctor output is not persisted.
- It rejects `danger-full-access` and other unapproved sandbox values.
- It rejects approval policies other than `on-request` or `untrusted`.
- It invokes Codex as:
  `codex --sandbox workspace-write --ask-for-approval on-request exec --json --cd <worktree> --color never -`.
- It passes the rendered prompt through stdin, not command-line arguments.
- It masks the task worktree path in command-log summaries as `<worktree>`.
- It never commits, merges, pushes, or applies changes to the main branch.

The smoke task is expected to create only `smoke/codex_worker_smoke.txt` in the
task worktree. The independent Review Worker accepts the result only if
`DiffCollector` reports no forbidden files, no disallowed commands, and no
suspicious secret markers. Task metadata cannot widen the real CLI file scope
beyond `smoke/**`.

## Local Real Codex Small Code Task Path

The small code-task path uses the same `LocalCodexCliClient` but requires the
separate opt-in `AI_ORG_ENABLE_REAL_CODEX_CODE_TASK=true` and task metadata
`codex_mode="local_code_task"`.

Current allowed files are fixed in policy:

- `src/ai_org/adapters/codex/smoke_helpers.py`
- `tests/unit/test_codex_smoke_helpers.py`

Task metadata cannot widen this scope. The code task still uses
`workspace-write`, `on-request`, stdin prompt delivery, a task worktree,
sanitized command logs, `DiffCollector`, logical artifact URIs, and independent
Review Worker acceptance. It does not commit, merge, push, or change the main
working tree.

When `sandbox_test_profile="real_code_task_smoke"` is present,
`DockerSandboxRunner` runs a fixed import/assert command inside the worktree. If
no sandbox runner is configured, the result records
`SANDBOX_RUNNER_NOT_CONFIGURED` and review requires rework instead of accepting
the task.

## Local Real Codex Multi-File Merge Candidate Path

The controlled multi-file path requires
`AI_ORG_ENABLE_REAL_CODEX_MULTI_FILE_TASK=true` and task metadata
`codex_mode="local_multi_file_task"`.

Current allowed files are fixed in policy:

- `src/ai_org/adapters/codex/merge_candidate.py`
- `tests/unit/test_codex_merge_candidate.py`

Task metadata cannot widen this scope. The same CLI preflight, worktree,
sanitized command-log, diff collection, and independent review boundaries apply.
`CodexWorker` also compares a main-worktree fingerprint before and after local
real Codex execution. The fingerprint includes `HEAD`, `git status
--porcelain=v1 --untracked-files=all`, tracked diffs, staged diffs, and
untracked file content hashes. If the main worktree changes, the result is
forced to FAILED with `MAIN_WORKTREE_MODIFIED` and `main_worktree:modified`.
The guard catches cases where `git status --short` is unchanged but dirty or
untracked file contents changed.

The prior real multi-file validation did not pass the stage because real Codex
also modified the main worktree. The current implementation treats that as a
hard failure and independent review rejects it. A successful MergeCandidate is
only possible when the task worktree diff is valid and the main-worktree
fingerprint is identical before and after execution.

After a later real multi-file revalidation attempt, the main-worktree
fingerprint stayed stable but the Codex CLI exec process timed out before
producing a diff. The current timeout handling classifies that failure as
`CODEX_CLI_TIMEOUT`, records timeout type, elapsed time, partial JSONL event
counts, last event type, approval-request observation, and process-tree cleanup
status, and still runs the main-worktree fingerprint post-check before returning
the failed result. Timeout results do not create accepted MergeCandidate
artifacts and are rejected by the Review Worker.

To reduce task complexity for the next real revalidation, the manual
multi-file task is now limited to the two code/test files above. Documentation
updates such as `docs/MERGE_APPROVAL.md` stay outside the real Codex task and
remain human/system-authored repository documentation.

After a successful task result, `CodexWorker` writes a `merge-candidate` JSON
artifact with logical URI
`artifact://codex/{task_id}/attempt-{n}/merge-candidate.json`. The summary is
generated by `MergeCandidateService` and explicitly records
`merge_performed=False`, `auto_merge=False`, `auto_push=False`,
`human_approval_required=True`, and
`approval_state="waiting_merge_approval"`.

After independent Review Worker acceptance, the application writes a
`merge_candidate.created` audit event. No code path commits, merges, pushes,
deletes worktrees, opens PRs, or deploys.

## Local Real Codex Stepwise Multi-File Merge Candidate Path

The stepwise multi-file path is the current recovery path for the single-call
multi-file timeout. It requires
`AI_ORG_ENABLE_REAL_CODEX_STEPWISE_MULTI_FILE_TASK=true` and task metadata
`codex_mode="local_stepwise_multi_file_task"`.

The logical task is split by `CodexWorker` into fixed single-file steps:

- Step 1 may modify only `src/ai_org/adapters/codex/merge_candidate.py` and
  forbids `tests/**`.
- Step 2 may modify only `tests/unit/test_codex_merge_candidate.py` and forbids
  `src/**`.

Each step is a separate Codex CLI invocation using the task worktree as `cwd`
and `--cd <worktree>`. Step prompts are short, use repository-relative paths
only, forbid secret output, forbid main-branch modification, and forbid merge,
commit, push, docs, config, workflow, dependency, and MergeService changes.

After each step, `CodexWorker` records the main-worktree fingerprint before and
after the step, compares task-worktree dirty-file fingerprints, checks the
single-file allowed scope, normalizes step timeout diagnostics to
`CODEX_STEP_TIMEOUT`, and stops on the first failure. If all steps succeed, a
fixed sandbox test runs through `SandboxRunner`. Only then can the normal
MergeCandidate artifact be written. The artifact remains a human-review surface:
it records no merge, no auto-merge, no auto-push, and required human merge
approval. It is not a MergeService and it does not perform branch operations.

## Local Real Codex CLI Diagnostics Path

The current manual recovery stage no longer asks real Codex to complete a
multi-file task. Instead, `tests/manual/test_real_codex_cli_diagnostics.py`
uses `AI_ORG_ENABLE_REAL_CODEX_DIAGNOSTICS=true` to run minimal CLI diagnostics
in an independent temporary Git repository.

The diagnostic path records:

- `codex --version`;
- `codex doctor --json` summarized without raw auth details;
- a read-only `codex exec --json --cd <worktree>` prompt that should reply
  exactly `OK`;
- stdin versus command-argument prompt shape comparison;
- a single-file create prompt limited to `diagnostic/codex_diag.txt`.

The diagnostics do not use the project source tree as Codex cwd, do not create
MergeCandidate artifacts, do not run Docker validation, do not commit, merge,
push, or enter MergeService work. The main-worktree fingerprint is recorded
before and after the diagnostics, and timeout results record JSONL event counts,
last event types, timeout classification, and process-tree cleanup metadata.
Default pytest and CI keep this path disabled.

## Human-Approved Merge Foundation

The current merge approval foundation does not call real Codex. It can consume
Mock, DryRun, or manual fixture MergeCandidates and requires explicit human
approval before the controlled `MergeService` path can run.

Real Codex facts remain unchanged: smoke and the small code task were
previously verified, while single-call multi-file, stepwise multi-file, and the
single-file create diagnostic are currently blocked by timeout on this host.
Those timeouts are not accepted MergeCandidates.

The controlled merge path operates on a configured repository or fixture,
checks clean worktree state, checks `HEAD == base_commit`, blocks forbidden
files and secret/path-bearing patches, applies the patch only in a temporary
integration clone, runs configured tests there, writes audit events, and never
pushes or deploys.

## AgentResult Metadata

Codex Worker metadata includes:

- `codex_mode`
- `worktree_path`
- `worktree_uri`
- `branch_name`
- `base_commit`
- `head_commit`
- `changed_files`
- `diff_summary`
- `tests_run`
- `command_logs`
- `blocked_reason`
- `policy_violations`
- `codex_preflight_passed`
- `codex_thread_observed`
- `codex_session_observed`
- `external_service_requested`
- `merge_candidate`
- `merge_candidate_artifact_uri`
- `merge_candidate_status`

Large diff and log content is written as artifact files under
`.ai_org_artifacts/`; prompt, diff, and command-log artifacts are sanitized
before writing. API responses expose logical artifact metadata and logical
worktree URIs, not local file paths or artifact contents.

## Not Implemented

- Codex MCP execution.
- Automatic merge to the main branch.
- Automatic merge approval.
- Running real Codex or arbitrary user commands inside Docker.
- Automatic commit of Codex output branches.
- OpenHands or other external agent runtime.
