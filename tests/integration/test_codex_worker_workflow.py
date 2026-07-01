from __future__ import annotations

import subprocess
from pathlib import Path

from ai_org.adapters.codex.clients import MockCodexClient
from ai_org.adapters.codex.worker import CodexWorker
from ai_org.adapters.memory.repositories import InMemoryRepository
from ai_org.adapters.workers.mock import DefaultWorkerRegistry, MockReviewWorker
from ai_org.application.service import ProjectApplicationService
from ai_org.domain.enums import ProjectStatus, TaskStatus, WorkerType
from ai_org.orchestration.workflow import LangGraphWorkflow
from ai_org.protocols.schemas import CreateProjectRequest, TaskSpec


def test_codex_mock_worker_completes_with_independent_review(tmp_path: Path) -> None:
    service, workflow, repo_path = _service_with_mock_codex(tmp_path)
    project = service.create_project(
        CreateProjectRequest(
            title="Codex mock",
            goal="Exercise coding worker",
            tasks=[
                TaskSpec(
                    title="Code",
                    objective="Create an isolated deterministic artifact",
                    worker_type=WorkerType.CODEX,
                    metadata={
                        "codex_mode": "mock",
                        "mock_output_file": "src/generated.txt",
                        "allowed_files": ["src/generated.txt"],
                    },
                )
            ],
        )
    )

    status = workflow.run(project.project_id)

    assert status.project.status == ProjectStatus.COMPLETED
    assert status.tasks[0].status == TaskStatus.ACCEPTED
    production_runs = [
        run for run in status.worker_runs if run.worker_type == WorkerType.CODEX.value
    ]
    review_runs = [run for run in status.worker_runs if run.worker_type == WorkerType.REVIEW.value]
    assert len(production_runs) == 1
    assert len(review_runs) == 1
    assert production_runs[0].structured_output is not None
    assert production_runs[0].structured_output["metadata"]["changed_files"] == [
        "src/generated.txt"
    ]
    assert _git(repo_path, "status", "--short").strip() == ""
    assert "coding_worker.completed" in [
        event.event_type for event in service.repo.list_audit_events(project.project_id)
    ]


def test_codex_mock_worker_run_is_idempotent(tmp_path: Path) -> None:
    service, workflow, _repo_path = _service_with_mock_codex(tmp_path)
    project = service.create_project(
        CreateProjectRequest(
            title="Codex idempotent",
            goal="Do not duplicate worker runs",
            tasks=[
                TaskSpec(
                    title="Code",
                    objective="Create once",
                    worker_type=WorkerType.CODEX,
                    metadata={"codex_mode": "mock"},
                )
            ],
        )
    )

    first = workflow.run(project.project_id)
    second = workflow.run(project.project_id)

    assert first.project.status == second.project.status == ProjectStatus.COMPLETED
    assert len(first.worker_runs) == len(second.worker_runs) == 2


def test_codex_failed_tests_stop_at_max_attempts(tmp_path: Path) -> None:
    service, workflow, _repo_path = _service_with_mock_codex(tmp_path)
    project = service.create_project(
        CreateProjectRequest(
            title="Codex rework",
            goal="Stop rework",
            tasks=[
                TaskSpec(
                    title="Code",
                    objective="Fail deterministic coding checks",
                    worker_type=WorkerType.CODEX,
                    max_attempts=2,
                    metadata={
                        "codex_mode": "mock",
                        "simulate_test_failure": True,
                        "allowed_commands": ["pytest"],
                        "required_tests": ["pytest tests/unit/test_codex_worker.py"],
                    },
                )
            ],
        )
    )

    status = workflow.run(project.project_id)

    assert status.project.status == ProjectStatus.BLOCKED
    assert status.tasks[0].status == TaskStatus.BLOCKED
    assert status.tasks[0].attempt_count == 2
    assert (
        len([run for run in status.worker_runs if run.worker_type == WorkerType.CODEX.value]) == 2
    )


def _service_with_mock_codex(
    tmp_path: Path,
) -> tuple[ProjectApplicationService, LangGraphWorkflow, Path]:
    repo_path = _git_repo(tmp_path / "repo")
    repo = InMemoryRepository()
    registry = DefaultWorkerRegistry(
        workers={
            WorkerType.CODEX.value: CodexWorker(repo_path, client=MockCodexClient()),
        },
        review_worker=MockReviewWorker(),
    )
    service = ProjectApplicationService(repo, registry)
    return service, LangGraphWorkflow(service), repo_path


def _git_repo(path: Path) -> Path:
    path.mkdir()
    _git(path, "init")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "AI Org Test")
    (path / "README.md").write_text("initial\n", encoding="utf-8")
    (path / ".gitignore").write_text(".ai_org_artifacts/\n.ai_org_worktrees/\n", encoding="utf-8")
    _git(path, "add", "README.md", ".gitignore")
    _git(path, "commit", "-m", "initial")
    return path


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=False,
        text=True,
        capture_output=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr)
    return result.stdout
