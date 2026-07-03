# Merge Approval Implementation Report

Status: WAITING FOR USER APPROVAL

## 1. Stage Goal

Implement and verify a human-approved controlled merge workflow without
depending on real Codex CLI. The stage uses Mock, DryRun, and manual fixture
MergeCandidates to validate approval, policy checks, patch apply, tests, audit
events, API behavior, and CI.

## 2. Current Status

Implementation and local validation are complete in this report revision. CI
run id and independent reviewer evidence will be updated after verification.

## 3. Why The Goal Changed

Real Codex CLI on the current host is unstable for write-path execution.
Single-call multi-file, stepwise multi-file, and single-file create diagnostics
timed out. Those failures remain blocked and are not reported as passing
MergeCandidates.

## 4. Real Codex CLI Current Status

- Real Codex smoke: previously verified.
- Real Codex small code task: previously verified.
- Real Codex multi-file: blocked by timeout.
- Real Codex stepwise multi-file: blocked by timeout.
- Real Codex single-file diagnostic create: blocked by timeout on current host.
- This stage does not call real Codex CLI.

## 5. MergeCandidate Design

`MergeCandidate` records candidate, project, task, worker-run, source type,
base commit, candidate branch or logical worktree URI, changed files, bounded
diff summary, logical patch artifact URI, tests summary, review decision,
human approval requirement, no-auto flags, lifecycle status, timestamps, and
approval metadata.

Large diffs remain in artifact storage addressed by logical URI; they are not
stored inline in API responses.

## 6. MergeApprovalService Design

`MergeApprovalService` creates waiting approval requests, lists and fetches
candidates, approves only reviewed waiting candidates, rejects waiting
candidates, blocks failed merge candidates, marks controlled merge results, and
writes audit events. Illegal transitions return conflict errors.

## 7. MergeService Design

`MergeService` requires an approved candidate, a clean target repository,
`HEAD == base_commit`, safe changed files, a readable logical patch artifact,
no secret-like patch content, no local absolute paths, no high-risk file
changes, and passing tests in a temporary integration clone. It records blocked
or merged results and audit events.

## 8. Real Codex Called

No.

## 9. Automatic Merge

No unapproved candidate can enter the merge path. The controlled merge path
operates only after explicit approval.

## 10. Automatic Push

No.

## 11. Automatic Deploy

No.

## 12. Approval Flow

`WAITING_APPROVAL -> APPROVED -> MERGED` is allowed only after accepted review,
human approval, policy checks, patch apply, and test success. `WAITING_APPROVAL
-> REJECTED` is allowed by explicit rejection. Failures in merge checks move
the candidate to `BLOCKED`.

## 13. Forbidden File Checks

The service blocks `.git/**`, `.github/**`, `.env*`, dependency files,
`pyproject.toml`, `alembic/**`, and `scripts/**` in both candidate changed
files and patch headers. Patch headers must also be covered by candidate
`changed_files`.

## 14. Secret And Path Sanitization

Patch content is blocked when it contains secret-like patterns or local
absolute paths. API responses expose logical artifact URIs and bounded
summaries, not raw patches.

## 15. Base Commit Check

Merge is blocked as `BASE_CHANGED_BLOCKED` when the target repository `HEAD`
does not match the candidate base commit.

## 16. Test Execution Path

Tests run in a temporary integration clone after patch apply. The default API
container has no production repository configured, so API merge attempts
without configuration return conflict.

## 17. API Endpoints

- `GET /merge-candidates/{candidate_id}`
- `GET /projects/{project_id}/merge-candidates`
- `POST /merge-candidates/{candidate_id}/approval`
- `POST /merge-candidates/{candidate_id}/merge`

## 18. Database And Migration Changes

No database migration is added in this stage. MergeCandidate and patch artifact
stores are in-memory application services for the current foundation.

## 19. Audit Events

Implemented event types include `merge_candidate.waiting_approval`,
`merge_approval.approved`, `merge_approval.rejected`,
`merge_candidate.blocked`, `merge_candidate.merged`,
`merge_service.blocked`, and `merge_service.merged`.

## 20. Local Test Results

- `.\.venv\Scripts\python.exe -m ruff format --check .`: exit `0`.
- `.\.venv\Scripts\python.exe -m ruff check .`: exit `0`.
- `.\.venv\Scripts\python.exe -m mypy src tests`: exit `0`.
- `.\.venv\Scripts\python.exe -m pytest tests\unit\test_merge_approval_service.py tests\unit\test_merge_service.py tests\e2e\test_merge_candidates_api.py -q`:
  `14 passed, 1 warning`.
- `.\.venv\Scripts\python.exe -m pytest -q`: `141 passed, 2 skipped, 1 warning`.
- `.\scripts\supply_chain_checks.ps1 -Python .\.venv\Scripts\python.exe`:
  exit `0`; `pip-audit` reported no known vulnerabilities;
  `detect-secrets` reported `0` findings; license report and CycloneDX SBOM
  were generated.
- `git diff --check`: exit `0`.

## 21. CI Run ID

Pending.

## 22. CI Run URL

Pending.

## 23. CI Commit Hash

Pending.

## 24. Reviewer Findings

Pending independent reviewer.

## 25. Known Risks

- MergeCandidate/MergeResult persistence is currently in memory.
- The controlled merge success path applies and tests in an integration clone;
  production branch merge remains a later explicit design.
- Real Codex write-path execution remains blocked on this host.

## 26. Unfinished Content

- Persistent merge-candidate database tables.
- Production branch merge, rollback, and PR workflow.
- Real Codex runtime repair or alternate execution environment evaluation.

## 27. Next Stage Recommendation

After acceptance, move to real Codex runtime repair or alternate execution
environment evaluation while keeping merge approval gates intact.

## 28. Current Branch

`master`

## 29. Current Commit Hash

`67aeac4893f29113100ccceb2e2576cf31ef754c` before this implementation commit.

## 30. Origin Master Commit Hash

`67aeac4893f29113100ccceb2e2576cf31ef754c` before this implementation commit.

## 31. Git Status

Dirty before implementation commit; expected changed files are the merge
approval implementation, tests, CI workflow, documentation, and this report.

## 32. User Acceptance Options

- Pass: enter real Codex runtime repair or alternate execution-environment
  evaluation.
- Wait: merge approval is implemented while real Codex remains disabled.
- Reject: continue fixing the human-approved merge foundation.
- Pause: do not continue for now.
- Adjust goal: re-plan the next stage.
