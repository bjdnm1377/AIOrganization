# Codex Coding Worker Isolation Acceptance Report

Status: VERIFIED COMPLETE FOR MOCK/DRY-RUN CODEX WORKER

## 1. Stage Goal

Implement Codex as a second-layer Coding Worker controlled by the first-layer AI
Organization workflow, using task-scoped Git worktrees, structured AgentResult
output, independent review, audit records, and FastAPI query access. Default
tests must use Mock/DryRun behavior and must not require real Codex credentials.

## 2. Current Result

Local implementation, local verification, independent review, and real GitHub
Actions Python 3.12 verification are complete for the Mock/DryRun Codex Worker
path. Real Codex execution remains intentionally unimplemented.

## 3. Completed Content

- Added `CodexClient` port and deterministic Mock/DryRun/NOT_CONFIGURED clients.
- Added `CodexWorker` behind the existing WorkerRegistry.
- Added task-scoped Git worktree creation and branch naming.
- Added constrained prompt rendering.
- Added diff, changed-file, created-file, deleted-file, binary-file, oversized
  diff, and simple secret-marker detection.
- Added structured command log collection and sanitization.
- Added independent Review Worker gating for coding policy violations and failed
  tests.
- Added Task metadata persistence with Alembic migration.
- Added FastAPI WorkerRun and artifact metadata query endpoints.
- Added Codex Worker unit, integration, and e2e tests.
- Updated CI workflow to run Coding Worker isolation tests.

## 4. Not Completed

- Real Codex CLI/MCP execution.
- Real Codex authentication.
- Automatic merge to main branch.
- Docker code-execution sandbox.
- Automatic worktree/artifact cleanup.

## 5. Files Added Or Modified

Key added files:

- `src/ai_org/ports/codex.py`
- `src/ai_org/adapters/codex/*`
- `tests/unit/test_worktree_service.py`
- `tests/unit/test_codex_worker.py`
- `tests/integration/test_codex_worker_workflow.py`
- `alembic/versions/0002_add_task_metadata.py`
- `docs/CODEX_WORKER.md`
- `docs/WORKTREE_ISOLATION.md`
- `docs/CODING_WORKER_SECURITY.md`

Key modified files:

- `.github/workflows/verification.yml`
- `src/ai_org/adapters/workers/mock.py`
- `src/ai_org/application/service.py`
- `src/ai_org/adapters/api/main.py`
- `src/ai_org/adapters/postgres/models.py`
- `src/ai_org/adapters/postgres/repositories.py`
- `docs/API.md`
- `docs/TESTING.md`
- `docs/THREAT_MODEL.md`

## 6. Architecture

`CodexWorker` implements the Worker port and delegates runtime behavior to the
`CodexClient` port. The current clients are deterministic and local-only:

- `MockCodexClient`: simulates file changes inside the task worktree.
- `DryRunCodexClient`: records a dry-run result.
- `LocalCodexCliClient`: returns NOT_CONFIGURED and does not invoke real Codex.

## 7. Worktree Isolation

`WorktreeService` creates one worktree per task attempt under
`.ai_org_worktrees/`, rejects roots that resolve outside the repo, sanitizes
path/branch components, records base/head commits, and never merges changes back
to the main branch automatically.

## 8. Diff And Logs

`DiffCollector` writes sanitized patch artifacts under `.ai_org_artifacts/` and
records a summary in AgentResult metadata. `CommandLogCollector` writes
sanitized JSON log artifacts and records command metadata including cwd, exit
code, timeout, network request flag, allowed flag, and approval flag. Prompt
artifacts are also sanitized before writing.

## 9. Permission And Approval Policy

Coding policy is driven by task metadata: allowed/forbidden files,
allowed/forbidden commands, required tests, and deterministic simulation flags.
Task metadata can add forbidden file patterns but cannot remove the system
baseline forbidden patterns. The Review Worker rejects policy violations and
NOT_CONFIGURED real-runtime results. Failed coding tests trigger bounded rework
until `max_attempts`.

## 10. Database And Protocol Changes

- Added `Task.metadata` to the domain model and Pydantic `TaskResponse`.
- Added `tasks.metadata` JSON column through Alembic migration
  `0002_add_task_metadata.py`.
- Extended Codex `AgentResult.metadata` with worktree, diff, test, command-log,
  session, and blocked-reason fields.

## 11. API Changes

Added:

- `GET /projects/{project_id}/worker-runs`
- `GET /tasks/{task_id}/worker-runs`
- `GET /worker-runs/{run_id}`
- `GET /worker-runs/{run_id}/artifacts`

## 12. Local Test Results

Local host Python: 3.13.13 from `.venv`.

| Command | Result |
| --- | --- |
| `.venv\Scripts\python.exe -m ruff format .` | exit 0 |
| `.venv\Scripts\python.exe -m ruff check .` | exit 0 |
| `.venv\Scripts\python.exe -m mypy src tests` | exit 0 |
| `.venv\Scripts\python.exe -m pytest tests/integration/test_alembic_and_postgres.py -q` | exit 0, 2 passed |
| `.venv\Scripts\python.exe -m pytest -q` | exit 0, 44 passed, 1 skipped, 1 warning |
| `powershell -ExecutionPolicy Bypass -File scripts/supply_chain_checks.ps1 -Python .\.venv\Scripts\python.exe` | exit 0 |
| `git diff --check` | exit 0 |

Supply chain local result:

- `pip-audit`: No known vulnerabilities found.
- `detect-secrets`: 0 findings.
- License report generated under ignored `reports/`.
- SBOM generated under ignored `reports/`.

## 13. CI Result

Verified by real GitHub Actions:

- Workflow: `Verification`
- Run id: `28535023081`
- Run URL: `https://github.com/bjdnm1377/AIOrganization/actions/runs/28535023081`
- Job id: `84594077281`
- Job URL:
  `https://github.com/bjdnm1377/AIOrganization/actions/runs/28535023081/job/84594077281`
- Branch: `master`
- Commit: `863342e0cdd0e5ccb7bdcca1c6c8638f7f7db0ab`
- Trigger: `push`
- Runner: GitHub-hosted Ubuntu runner
- PostgreSQL image: `postgres:16.6`
- Started: `2026-07-01T17:15:13Z`
- Completed: `2026-07-01T17:16:51Z`
- Conclusion: `success`

Successful CI steps included Python 3.12 setup, requirements-lock validation,
ruff format/check, mypy, Alembic migration against PostgreSQL, PostgreSQL
repository/checkpoint recovery tests, workflow scenarios A-E, FastAPI e2e,
checkpoint security tests, Codex Coding Worker isolation tests, full pytest,
pip-audit, license report, SBOM generation, detect-secrets, and git whitespace
check.

## 14. Reviewer Findings

Independent Reviewer findings and handling:

- High: task metadata could clear default forbidden files. Fixed by always
  merging task forbidden patterns with the immutable system baseline; added
  regression test.
- High: command policy checked only `simulated` command logs. Fixed by checking
  all executed command logs except explicit `skipped` and `not_configured`
  entries; added regression test.
- Medium: secret-like prompt/diff content could be written to artifacts before
  review rejected it. Fixed by sanitizing prompt and diff artifacts before
  writing and by using logical artifact URIs; added regression test.
- Low: NOT_CONFIGURED WorkerRun is still recorded as a completed worker run so
  review can persist a structured rejection. This remains documented as a status
  semantics caveat for later refinement.

All high and medium Reviewer findings with evidence were fixed before commit.

## 15. Known Risks

- Real Codex runtime is intentionally not implemented.
- Local verification used Python 3.13; Python 3.12 verification must come from
  GitHub Actions.
- Worktree cleanup is manual.
- Policy is deterministic and conservative, not a production sandbox.

## 16. Next Stage Recommendation

After CI passes and user accepts this stage, proceed to a controlled real Codex
Worker smoke test with explicit opt-in authentication and non-production scope.

## 17. Git State

- Branch: `master`
- Verified implementation commit:
  `863342e0cdd0e5ccb7bdcca1c6c8638f7f7db0ab`
- Final report commit: reported in final response.

## 18. User Acceptance Options

- Pass: enter real Codex Worker controlled smoke test stage.
- Wait: keep the current DryRun/Mock implementation and do not enable real Codex.
- Reject: continue fixing Codex Worker isolation stage.
- Pause: stop for now.
- Adjust target: re-plan the next stage.
