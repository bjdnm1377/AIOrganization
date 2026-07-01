from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from ai_org.adapters.codex.clients import LocalCodexCliClient
from ai_org.adapters.codex.worker import CodexWorker
from ai_org.adapters.memory.repositories import InMemoryRepository
from ai_org.adapters.workers.mock import DefaultWorkerRegistry, MockReviewWorker
from ai_org.application.service import ProjectApplicationService
from ai_org.domain.enums import ProjectStatus, TaskStatus, WorkerType
from ai_org.orchestration.workflow import LangGraphWorkflow
from ai_org.protocols.schemas import CreateProjectRequest, TaskSpec

pytestmark = pytest.mark.manual_codex


@pytest.mark.skipif(
    os.environ.get("AI_ORG_ENABLE_REAL_CODEX_SMOKE", "").lower() != "true",
    reason="real Codex CLI smoke test requires explicit opt-in",
)
@pytest.mark.skipif(shutil.which("codex") is None, reason="Codex CLI is not installed")
def test_real_codex_cli_smoke_isolated_worktree(tmp_path: Path) -> None:
    repo_path = _git_repo(tmp_path / "repo")
    repo = InMemoryRepository()
    registry = DefaultWorkerRegistry(
        workers={
            WorkerType.CODEX.value: CodexWorker(
                repo_path,
                client=LocalCodexCliClient(timeout_seconds=180),
            ),
        },
        review_worker=MockReviewWorker(),
    )
    service = ProjectApplicationService(repo, registry)
    workflow = LangGraphWorkflow(service)
    project = service.create_project(
        CreateProjectRequest(
            title="Real Codex smoke",
            goal="Verify controlled real Codex CLI smoke path",
            tasks=[
                TaskSpec(
                    title="Create smoke file",
                    objective=(
                        "Create or overwrite smoke/codex_worker_smoke.txt with exactly "
                        "three lines: AI Organization Codex real smoke test; "
                        "task_id will be provided in the prompt; no secrets. "
                        "Do not modify any other file."
                    ),
                    worker_type=WorkerType.CODEX,
                    metadata={
                        "codex_mode": "local_cli",
                        "allowed_files": ["smoke/**"],
                        "codex_sandbox": "workspace-write",
                        "codex_approval_policy": "on-request",
                    },
                    acceptance_criteria=["real codex smoke reviewed independently"],
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
    assert len(production_runs) == 1
    output = production_runs[0].structured_output
    assert output is not None
    metadata = output["metadata"]
    assert metadata["codex_mode"] == "local_cli"
    assert metadata["no_real_codex_started"] is False
    assert metadata["changed_files"] == ["smoke/codex_worker_smoke.txt"]
    assert metadata["policy_violations"] == []
    assert all(artifact["uri"].startswith("artifact://codex/") for artifact in output["artifacts"])
    assert _git(repo_path, "status", "--short").strip() == ""
    assert "coding_worker.completed" in [
        event.event_type for event in service.repo.list_audit_events(project.project_id)
    ]


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
