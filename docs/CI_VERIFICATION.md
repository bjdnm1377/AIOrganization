# CI Verification

Date: 2026-07-01

## Status

Status: CI WORKFLOW READY / WAITING FOR CI RUN

The repository now contains `.github/workflows/verification.yml`. The workflow is
designed to complete the checks that are blocked on the current Windows host:
Python 3.12 baseline verification, real PostgreSQL integration, Alembic
migration execution, and LangGraph PostgreSQL checkpoint interrupt/resume.

This document does not claim that CI has passed. A passing GitHub Actions run is
still required before the project can enter the Codex Coding Worker isolation
stage.

## Python Baseline

The project keeps Python `3.12.x` as the verification baseline. `pyproject.toml`
still allows `>=3.12,<3.15`, but the GitHub Actions verification job uses
`actions/setup-python` with `python-version: "3.12"`.

The baseline was not changed to Python 3.13. Python 3.13 remains only the local
fallback interpreter on the current host.

## PostgreSQL Service

The CI workflow uses a GitHub Actions service container:

- Image: `postgres:16.6`
- Database: `ai_org`
- User: `ai_org_app`
- Password: CI-only test value, marked allowlisted for secret scanning
- Health check: `pg_isready -U ai_org_app -d ai_org`

`postgres:16.6` was selected because it is a stable, widely available
PostgreSQL 16 patch image and is sufficient for SQLAlchemy, Alembic, psycopg,
and `langgraph-checkpoint-postgres` validation. The workflow avoids `latest`
and avoids the newer `postgres:18.4` image for CI baseline stability.

## CI Environment Variables

The workflow passes test-only URLs through environment variables:

- `AI_ORG_DATABASE_URL`
- `AI_ORG_CHECKPOINT_DATABASE_URL`
- `AI_ORG_USE_EXISTING_POSTGRES=true`
- `AI_ORG_CHECKPOINT_SETUP=true`

No production database, real API key, OpenAI key, GitHub token, or Codex
credential is used.

## Verification Steps

The workflow performs:

- Python 3.12 setup.
- Virtual environment creation.
- Installation from `requirements-lock.txt`.
- Local package installation with `pip install -e .`.
- `pip check`.
- Lock-file verification against installed distributions.
- `ruff format --check .`.
- `ruff check .`.
- `mypy src tests`.
- `alembic upgrade head` against the PostgreSQL service.
- PostgreSQL integration test covering migration, repository, approval
  interrupt, process-style recreation, checkpoint resume, and worker-run counts.
- Workflow scenario tests for low risk, high-risk approval resume, rejection,
  rework limit, and idempotency.
- FastAPI end-to-end tests.
- Checkpoint strict msgpack and unsafe-state tests.
- Full `pytest -q`.
- `pip-audit`.
- `pip-licenses`.
- CycloneDX SBOM generation.
- `detect-secrets` scan.
- `git diff --check`.

Generated scan outputs are uploaded as a GitHub Actions artifact named
`verification-reports`.

## Local Limitation

The current local host still lacks Python 3.12 and Docker. Local checks can
validate formatting, linting, type checking, in-memory tests, FastAPI tests, and
supply-chain scripts with the available Python 3.13 virtual environment. Local
PostgreSQL and Python 3.12 baseline verification remain blocked until Docker and
Python 3.12 are installed locally, or until GitHub Actions runs successfully.

## Acceptance Rule

Do not enter the Codex Coding Worker isolation stage until a real CI run of
`.github/workflows/verification.yml` passes, or an equivalent remote validation
environment produces auditable evidence for the same checks.
