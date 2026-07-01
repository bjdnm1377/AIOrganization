# Final Verification Report - CI Baseline Follow-up

Date: 2026-07-01

Stage: CI environment validation and version-baseline self-repair

Status: CI WORKFLOW READY / WAITING FOR CI RUN

## 1. Stage Goal

This phase addresses the environment baseline blockers recorded in the previous
verification report. The goal is to provide a CI path for Python 3.12,
`requirements-lock.txt`, PostgreSQL service integration, Alembic migrations,
PostgreSQL repository behavior, LangGraph PostgreSQL checkpoint interrupt/resume,
high-risk approval recovery, linting, typing, tests, secret scanning,
vulnerability scanning, license reporting, and SBOM generation.

This phase did not add business features and did not integrate a real LLM, real
Codex Worker, OpenHands, Virtuoso, HFSS, MATLAB, Redis, Temporal, or web
frontend.

## 2. Current Blocked State

The project remains blocked from entering the Codex Coding Worker isolation
stage.

Reason:

- The local host still does not have Python 3.12.
- The local host still does not have Docker.
- The new GitHub Actions workflow has been created but has not been observed
  passing in this local session.

Required gate:

- A real run of `.github/workflows/verification.yml` must pass, or an equivalent
  remote validation environment must produce auditable results for the same
  checks.

## 3. Actual Changes

- Created `.github/workflows/verification.yml`.
- Created `docs/CI_VERIFICATION.md`.
- Created `CI_PENDING_REPORT.md`.
- Updated `README.md` to make the Python 3.12 verification baseline explicit.
- Updated PostgreSQL integration test so it can use either a GitHub Actions
  PostgreSQL service or local Docker Compose.
- Changed the local Compose PostgreSQL image from `postgres:18.4` to
  `postgres:16.6` for a conservative fixed CI/local baseline.
- Updated testing, local-development, and dependency-update docs.
- Updated the supply-chain script to scan `.github` and the CI pending report.

## 4. Python Baseline

Baseline before this phase:

- Python `3.12.x`

Baseline after this phase:

- Python `3.12.x`

Changed:

- No.

Rationale:

- Python 3.12 remains the intended verification baseline.
- The local Python 3.13 interpreter is an environment fallback only.
- There is no evidence that LangGraph, FastAPI, Pydantic, SQLAlchemy, Alembic,
  psycopg, or the scan tools require raising the baseline.

Local interpreter used for local-only checks:

- Python `3.13.13`

This is not represented as Python 3.12 verification.

## 5. requirements-lock.txt

Regenerated:

- No.

Reason:

- The local host lacks Python 3.12. Regenerating the baseline lock from Python
  3.13 would not close the baseline gap.

CI verification:

- Install from `requirements-lock.txt`.
- Install the local package with `pip install -e .`.
- Run `pip check`.
- Compare pinned package versions in `requirements-lock.txt` against installed
  distributions under Python 3.12.

If CI fails this lock check, regenerate `requirements-lock.txt` in a Python 3.12
environment and commit the lock diff.

## 6. PostgreSQL Service

CI service configuration:

- Image: `postgres:16.6`
- Database: `ai_org`
- User: `ai_org_app`
- Password: CI-only test value, allowlisted for secret scanning
- Health check: `pg_isready -U ai_org_app -d ai_org`
- Environment URLs:
  - `AI_ORG_DATABASE_URL`
  - `AI_ORG_CHECKPOINT_DATABASE_URL`

Reason for `postgres:16.6`:

- Stable PostgreSQL 16 patch release.
- Fixed tag, not `latest`.
- Lower CI risk than starting the baseline on a newer PostgreSQL 18 image before
  checkpoint recovery is proven.

## 7. Alembic Migration Verification

CI command configured:

```bash
python -m alembic upgrade head
```

Local status:

- Not executed against a live PostgreSQL database because Docker is unavailable.
- Static migration declaration test passed locally.

## 8. PostgreSQL Checkpoint Interrupt/Resume

CI command configured:

```bash
python -m pytest tests/integration/test_alembic_and_postgres.py -q
```

The test now supports:

- GitHub Actions service mode with `AI_ORG_USE_EXISTING_POSTGRES=true`.
- Local Docker Compose fallback when no existing service is configured.
- Explicit local skip when neither a service nor Docker is available.

The test covers:

- Alembic migration.
- High-risk task approval interrupt.
- Approval record persistence.
- PostgreSQL checkpoint persistence.
- Repository/service/workflow recreation.
- Approval resume.
- Final completion.
- Worker-run count verification.

Local status:

- `1 passed, 1 skipped`; live PostgreSQL path skipped because Docker is missing.

## 9. Local Test Results

Commands actually run locally in this phase:

| Command | Exit | Passed | Failed | Skipped | Result |
| --- | ---: | ---: | ---: | ---: | --- |
| `.\.venv\Scripts\python -m ruff format .` | 0 | n/a | 0 | 0 | 1 file reformatted |
| `.\.venv\Scripts\python -m ruff format --check .` | 0 | n/a | 0 | 0 | 42 files already formatted |
| `.\.venv\Scripts\python -m ruff check .` | 0 | n/a | 0 | 0 | All checks passed |
| `.\.venv\Scripts\python -m mypy src tests` | 0 | n/a | 0 | 0 | No issues in 40 source files |
| `.\.venv\Scripts\python -m pytest -q` | 0 | 28 | 0 | 1 | PostgreSQL live path skipped |
| `.\.venv\Scripts\python -m pytest tests\integration\test_workflow_scenarios.py -q` | 0 | 6 | 0 | 0 | Scenarios A-E and idempotency |
| `.\.venv\Scripts\python -m pytest tests\e2e\test_api.py -q` | 0 | 3 | 0 | 0 | FastAPI e2e |
| `.\.venv\Scripts\python -m pytest tests\unit\test_checkpoint_security.py -q` | 0 | 5 | 0 | 0 | Strict msgpack and unsafe payload tests |
| `.\.venv\Scripts\python -m pytest tests\integration\test_alembic_and_postgres.py -q` | 0 | 1 | 0 | 1 | Live PostgreSQL skipped locally |
| `.\.venv\Scripts\python -m pytest tests\unit\test_postgres_repository.py -q` | 0 | 1 | 0 | 0 | Sanitized repository conflict |
| `.\scripts\supply_chain_checks.ps1` | 0 | n/a | 0 | 0 | Local scan suite passed |
| `git diff --check` | 0 | n/a | 0 | 0 | No whitespace errors |

## 10. CI Commands Configured

The workflow configures:

- Python 3.12 setup.
- `pip install -r requirements-lock.txt`.
- `pip install -e .`.
- `pip check`.
- lock-file package-version verification.
- `ruff format --check .`.
- `ruff check .`.
- `mypy src tests`.
- `alembic upgrade head`.
- PostgreSQL integration and checkpoint recovery tests.
- Workflow scenario tests.
- FastAPI e2e tests.
- Checkpoint security tests.
- Full pytest.
- `pip-audit`.
- `pip-licenses`.
- CycloneDX SBOM generation.
- `detect-secrets`.
- `git diff --check`.

## 11. Supply Chain And Secret Scan

Local results from `.\scripts\supply_chain_checks.ps1`:

- `pip-audit`: exit 0; dependencies audited: 106; known vulnerabilities: 0.
- `pip-licenses`: exit 0; license entries: 103.
- CycloneDX SBOM: exit 0; components: 107.
- `detect-secrets`: exit 0; findings: 0.

Generated reports remain under `reports/`, which is ignored by Git.

## 12. Security Confirmation

Confirmed:

- No real API keys were added.
- No real OpenAI key was requested or used.
- No real Codex Worker was started.
- No untrusted user code execution path was added.
- Pickle fallback remains disabled.
- Checkpoint state constraints were not weakened.
- CI PostgreSQL credential is a test-only value, not a production secret.

## 13. Reviewer Findings

Independent reviewer status:

- Completed read-only review before final commit.

High severity:

- None.

Medium severity:

- `FINAL_VERIFICATION_REPORT.md` still listed reviewer status as pending.
  Resolution: this section now records the completed review result.
- `ACCEPTANCE_REPORT.md` retained an old acceptance option that could imply
  immediate entry to the Codex Worker stage. Resolution: the acceptance options
  now require CI to pass before "Pass" is valid.

Low severity:

- GitHub Actions and PostgreSQL image tags are fixed but not pinned by
  SHA/digest. Resolution: accepted for this phase because the current
  requirement is fixed versions; digest pinning remains a future supply-chain
  hardening task.
- `README.md` could make Python 3.13 look like the verification baseline.
  Resolution: README now explicitly states that CI/verification baseline remains
  Python 3.12.

Reviewer confirmed:

- CI uses Python 3.12.
- PostgreSQL service is fixed to `postgres:16.6` with a health check and
  test-only credential.
- CI config includes Alembic, PostgreSQL checkpoint recovery, scenarios A-E,
  FastAPI e2e, checkpoint security, linting, typing, pytest, vulnerability
  scan, license report, SBOM, and secret scan.
- Reports do not claim CI has passed.
- No real LLM, real Codex Worker, or next-stage integration was added.

## 14. Known Issues

- CI workflow has not yet been observed passing.
- Python 3.12 remains unavailable locally.
- Docker remains unavailable locally.
- `requirements-lock.txt` remains generated from Python 3.13 until CI or another
  Python 3.12 environment validates or regenerates it.
- PostgreSQL role/grant hardening and checkpoint retention jobs remain future
  work.

## 15. Git Information

Current branch:

- `master`

Latest committed baseline before this phase:

- `b8268bc chore: verify environment baseline constraints`

The final commit hash for this phase cannot be embedded in this file before the
commit exists. The final assistant response records the immutable post-commit
hash and post-commit `git status --short`.

## 16. Can The Project Enter The Next Stage?

No.

The allowed user acceptance option for the current state is:

- Wait: CI workflow is ready, wait for actual CI run result.

## 17. User Acceptance Options

- Pass: CI has passed, enter Codex Coding Worker isolation stage.
- Wait: CI workflow is ready, wait for actual CI run result.
- Reject: continue fixing this CI verification stage.
- Pause: do not continue for now.
- Adjust goal: re-plan the next stage.
