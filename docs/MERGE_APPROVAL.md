# Merge Approval

## Current Status

The repository now has a minimal human-approved controlled merge foundation.
This stage does not depend on real Codex CLI execution. MergeCandidates can
come from Mock/DryRun clients, manual fixture patches, or blocked-real-Codex
fixtures used only as negative evidence.

Current real Codex status remains explicit:

- Real Codex smoke: previously verified.
- Real Codex small code task: previously verified.
- Real Codex single-call multi-file: blocked by timeout.
- Real Codex stepwise multi-file: blocked by timeout.
- Real Codex single-file diagnostic create: blocked by timeout on this host.

Those blocked results are not accepted as passing MergeCandidates. The current
merge approval foundation continues while real Codex stays disabled by default.

## MergeCandidate

`MergeCandidate` is a structured domain object, not a merge result. It records:

- candidate, project, task, and worker-run identifiers;
- source type: `mock`, `dry_run`, `manual_fixture`, or
  `real_codex_blocked_fixture`;
- base commit and either a candidate branch or logical worktree URI;
- repository-relative changed files;
- bounded diff summary and tests summary;
- logical `patch_artifact_uri`;
- Review Worker decision;
- `requires_human_merge_approval=True`;
- `auto_merge=False`;
- `auto_push=False`;
- status: `WAITING_APPROVAL`, `APPROVED`, `REJECTED`, `MERGED`, or `BLOCKED`;
- approval actor, reason, and timestamp fields.

Large diffs are not stored inline in normal database fields or API responses.
The patch is addressed by logical artifact URI, for example
`artifact://merge-candidates/example.patch`.

## MergeApprovalService

`MergeApprovalService` owns the approval state machine. It can create a
candidate approval request, list and fetch candidates, approve a waiting
candidate, reject a waiting candidate, block a candidate, and mark a candidate
merged after a controlled merge result.

Approval requires all of the following:

- the candidate exists;
- current status is `WAITING_APPROVAL`;
- `review_decision` is `ACCEPTED`;
- `requires_human_merge_approval=True`;
- `auto_merge=False`;
- `auto_push=False`;
- source type is not `real_codex_blocked_fixture`.

Illegal transitions raise conflict errors. Rejected, blocked, merged, or
already approved candidates cannot be silently approved again. Each approval,
rejection, blocked result, and merge result writes an audit event.

## MergeService

`MergeService` is intentionally minimal and controlled. It does not call real
Codex, does not push, does not deploy, and does not directly mutate the current
AIleader master worktree by default.

The implemented path:

1. Requires an `APPROVED` candidate.
2. Requires an explicitly configured target repository and test command.
3. Verifies the target repository is clean.
4. Verifies `HEAD` equals the candidate `base_commit`; otherwise the candidate
   is blocked with `BASE_CHANGED_BLOCKED`.
5. Rejects candidate and patch paths matching high-risk files such as
   `.git/**`, `.github/**`, `.env*`, dependency files, `pyproject.toml`,
   `alembic/**`, and `scripts/**`.
6. Reads the patch through `patch_artifact_uri`.
7. Blocks patches containing secret-like values or local absolute paths.
8. Blocks patches whose file headers are not covered by candidate
   `changed_files`.
9. Creates a temporary integration clone.
10. Applies the patch in that temporary clone.
11. Runs the configured tests in the temporary clone.
12. Records a blocked result on patch or test failure.
13. Records a merged result and audit event only after patch apply and tests
    pass in the controlled clone.

The success result still records `auto_push=False` and `auto_deploy=False`.
The implementation does not create PRs, push branches, deploy, delete Codex
worktrees, or bypass human approval.

## API

FastAPI exposes bounded merge-candidate endpoints:

- `GET /merge-candidates/{candidate_id}`;
- `GET /projects/{project_id}/merge-candidates`;
- `POST /merge-candidates/{candidate_id}/approval`;
- `POST /merge-candidates/{candidate_id}/merge`.

Responses use Pydantic models and expose summaries plus logical artifact URIs.
They do not inline raw patch content, local absolute paths, secrets, or
tracebacks. Missing resources return `404`; illegal transitions return `409`.

## Persistence

This stage uses an in-memory MergeCandidate store and an in-memory patch
artifact store attached to the application container. No database migration is
introduced in this stage. PostgreSQL project/task/approval/audit and checkpoint
tests remain unchanged and continue to run in CI.

## Review Boundary

Review remains independent from production. A candidate must not be treated as
merged merely because it exists. Review and merge checks reject:

- failed or timed-out real Codex results;
- blocked real Codex fixtures;
- candidates with forbidden files;
- candidates with secret-like patch content;
- patches with local absolute paths;
- candidates that request auto-merge or auto-push;
- candidates whose base commit no longer matches the target repository.

## Not Implemented

- Real Codex execution in this stage.
- Automatic merge of unapproved candidates.
- Automatic push.
- Automatic deploy.
- Pull request creation.
- Persistent merge-candidate database tables.
- Production-grade arbitrary-code execution.

Real Codex can be revalidated later in WSL/Linux, a different CLI version,
Codex App worktree, or a remote environment. Once real Codex is stable again,
its accepted output can enter this same approval chain as a candidate, but it
still cannot merge before human approval.
