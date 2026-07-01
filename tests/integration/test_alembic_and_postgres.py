from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

from ai_org.adapters.postgres.repositories import SqlAlchemyRepository
from ai_org.adapters.postgres.session import (
    build_engine,
    build_session_factory,
    configure_search_path,
)
from ai_org.adapters.workers.mock import DefaultWorkerRegistry
from ai_org.application.service import ProjectApplicationService
from ai_org.domain.enums import ProjectStatus, RiskLevel, TaskStatus, WorkerType
from ai_org.orchestration.postgres_checkpoint import postgres_checkpointer
from ai_org.orchestration.workflow import LangGraphWorkflow
from ai_org.protocols.schemas import ApprovalDecision, CreateProjectRequest, TaskSpec

TEST_DB_PASSWORD = f"test_{uuid4().hex}"
DEFAULT_SQLALCHEMY_URL = (
    f"postgresql+psycopg://ai_org_app:{TEST_DB_PASSWORD}@localhost:5432/ai_org?connect_timeout=5"
)
SQLALCHEMY_URL = os.environ.get("AI_ORG_DATABASE_URL", DEFAULT_SQLALCHEMY_URL)
PSYCOPG_URL = os.environ.get(
    "AI_ORG_CHECKPOINT_DATABASE_URL",
    SQLALCHEMY_URL.replace("postgresql+psycopg://", "postgresql://", 1),
)
USE_EXISTING_POSTGRES = os.environ.get("AI_ORG_USE_EXISTING_POSTGRES", "").lower() in {
    "1",
    "true",
    "yes",
}


def test_alembic_migration_declares_required_tables_and_schemas() -> None:
    migration = Path("alembic/versions/0001_initial_business_schema.py").read_text(encoding="utf-8")
    metadata_migration = Path("alembic/versions/0002_add_task_metadata.py").read_text(
        encoding="utf-8"
    )
    for token in (
        "ai_org",
        "langgraph_checkpoint",
        "projects",
        "tasks",
        "worker_runs",
        "approvals",
        "audit_events",
        "uq_worker_runs_idempotency_key",
    ):
        assert token in migration
    assert "metadata" in metadata_migration


@pytest.mark.postgres
def test_postgresql_migrations_and_checkpoint_recovery() -> None:
    managed_compose = not USE_EXISTING_POSTGRES
    if managed_compose:
        if not _docker_available():
            pytest.skip("Docker is unavailable and no existing PostgreSQL service was configured")
        _compose("up", "-d", "postgres")

    try:
        if managed_compose:
            _wait_for_compose_postgres()
        _wait_for_database_url(PSYCOPG_URL)
        _run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            env={
                **os.environ,
                "AI_ORG_DATABASE_URL": _with_connect_timeout(SQLALCHEMY_URL),
                "AI_ORG_POSTGRES_PASSWORD": TEST_DB_PASSWORD,
            },
        )

        engine = build_engine(SQLALCHEMY_URL)
        session_factory = build_session_factory(engine)
        session = session_factory()
        configure_search_path(session)
        try:
            repo = SqlAlchemyRepository(session)
            service = ProjectApplicationService(repo, DefaultWorkerRegistry.create())
            project = service.create_project(
                CreateProjectRequest(
                    title="PostgreSQL checkpoint smoke",
                    goal="Verify high-risk resume from PostgreSQL checkpoint",
                    success_criteria=["approval resumes"],
                    tasks=[
                        TaskSpec(
                            title="High-risk smoke task",
                            objective="Exercise checkpoint resume",
                            worker_type=WorkerType.RESEARCH,
                            risk_level=RiskLevel.HIGH,
                            acceptance_criteria=["approval resumes"],
                        )
                    ],
                )
            )
            session.commit()

            with postgres_checkpointer(PSYCOPG_URL, setup=True) as saver:
                workflow = LangGraphWorkflow(service, checkpointer=saver)
                first_status = workflow.run(project.project_id)
            session.commit()

            approvals = repo.list_approvals(project.project_id)
            task = repo.list_tasks(project.project_id)[0]
            assert first_status.project.status == ProjectStatus.WAITING_APPROVAL
            assert len(approvals) == 1
            assert len(repo.list_worker_runs(task.task_id)) == 0

            approval_id = approvals[0].approval_id
            session.close()
            session = session_factory()
            configure_search_path(session)
            repo = SqlAlchemyRepository(session)
            service = ProjectApplicationService(
                repo,
                DefaultWorkerRegistry.create(),
                commit=session.commit,
                rollback=session.rollback,
            )

            with postgres_checkpointer(PSYCOPG_URL) as saver:
                resumed = LangGraphWorkflow(service, checkpointer=saver)
                final_status = resumed.resume(
                    project.project_id,
                    approval_id,
                    ApprovalDecision(decision="APPROVED", decision_reason="docker smoke"),
                )
            session.commit()

            task = repo.list_tasks(project.project_id)[0]
            assert final_status.project.status == ProjectStatus.COMPLETED
            assert task.status == TaskStatus.ACCEPTED
            assert len(repo.list_worker_runs(task.task_id)) == 2
        finally:
            session.close()
            engine.dispose()
    finally:
        if managed_compose:
            _compose("down", "-v", "--remove-orphans", check=False)


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    return _run(["docker", "compose", "version"], check=False).returncode == 0


def _compose(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return _run(
        ["docker", "compose", *args],
        check=check,
        env={**os.environ, "AI_ORG_POSTGRES_PASSWORD": TEST_DB_PASSWORD},
    )


def _run(
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        check=False,
        cwd=Path(__file__).resolve().parents[2],
        env=env,
        text=True,
        capture_output=True,
        timeout=120,
    )
    if check and result.returncode != 0:
        pytest.fail(
            f"Command failed: {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    return result


def _wait_for_compose_postgres() -> None:
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        result = _compose(
            "exec",
            "-T",
            "postgres",
            "pg_isready",
            "-U",
            "ai_org_app",
            "-d",
            "ai_org",
            check=False,
        )
        if result.returncode == 0:
            return
        time.sleep(2)
    pytest.fail("PostgreSQL container did not become ready within 90 seconds")


def _wait_for_database_url(url: str) -> None:
    deadline = time.monotonic() + 90
    last_error = ""
    while time.monotonic() < deadline:
        try:
            with (
                psycopg.connect(url, connect_timeout=3) as connection,
                connection.cursor() as cursor,
            ):
                cursor.execute("select 1")
            return
        except psycopg.OperationalError as exc:
            last_error = str(exc)
            time.sleep(2)
    pytest.fail(f"PostgreSQL service did not become ready within 90 seconds: {last_error}")


def _with_connect_timeout(url: str) -> str:
    if "connect_timeout=" in url:
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}connect_timeout=5"
