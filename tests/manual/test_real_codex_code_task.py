from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from ai_org.adapters.codex.clients import LocalCodexCliClient
from ai_org.adapters.codex.worker import CodexWorker
from ai_org.adapters.memory.repositories import InMemoryRepository
from ai_org.adapters.sandbox import DockerSandboxRunner
from ai_org.adapters.workers.mock import DefaultWorkerRegistry, MockReviewWorker
from ai_org.application.service import ProjectApplicationService
from ai_org.domain.enums import ProjectStatus, TaskStatus, WorkerType
from ai_org.orchestration.workflow import LangGraphWorkflow
from ai_org.protocols.schemas import CreateProjectRequest, TaskSpec

pytestmark = pytest.mark.manual_codex_code_task

ALLOWED_FILES = [
    "src/ai_org/adapters/codex/smoke_helpers.py",
    "tests/unit/test_codex_smoke_helpers.py",
]


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        result = subprocess.run(
            ["docker", "info"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


@pytest.mark.skipif(
    os.environ.get("AI_ORG_ENABLE_REAL_CODEX_CODE_TASK", "").lower() != "true",
    reason="real Codex CLI code-task test requires explicit opt-in",
)
@pytest.mark.skipif(shutil.which("codex") is None, reason="Codex CLI is not installed")
@pytest.mark.skipif(not _docker_available(), reason="Docker is not available")
def test_real_codex_small_code_task_uses_worktree_and_sandbox() -> None:
    repo_path = Path(__file__).resolve().parents[2]
    before_status = _git(repo_path, "status", "--short")
    repo = InMemoryRepository()
    registry = DefaultWorkerRegistry(
        workers={
            WorkerType.CODEX.value: CodexWorker(
                repo_path,
                client=LocalCodexCliClient(timeout_seconds=240),
                sandbox_runner=DockerSandboxRunner(),
            ),
        },
        review_worker=MockReviewWorker(),
    )
    service = ProjectApplicationService(repo, registry)
    workflow = LangGraphWorkflow(service)
    project = service.create_project(
        CreateProjectRequest(
            title="Real Codex code task",
            goal="Verify controlled real Codex small code-task path",
            tasks=[
                TaskSpec(
                    title="Create Codex smoke helper",
                    objective=(
                        "Create exactly two files and no other files. "
                        "File 1: src/ai_org/adapters/codex/smoke_helpers.py. "
                        "Implement format_smoke_metadata(metadata: dict[str, object]) -> str. "
                        "It must return '<empty>' for an empty dict; sort keys lexicographically; "
                        "format str values unchanged; bool values as true/false; None as null; "
                        "int and float values with str(value); and all other value types as "
                        "'<complex>'. Join entries as 'key=value' with ', '. "
                        "File 2: tests/unit/test_codex_smoke_helpers.py. Add tests for empty "
                        "metadata and sorted primitive formatting. Do not modify any other file."
                    ),
                    worker_type=WorkerType.CODEX,
                    max_attempts=1,
                    metadata={
                        "codex_mode": "local_code_task",
                        "codex_sandbox": "workspace-write",
                        "codex_approval_policy": "on-request",
                        "sandbox_test_profile": "real_code_task_smoke",
                    },
                    acceptance_criteria=["real codex code task reviewed independently"],
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
    assert metadata["codex_mode"] == "local_code_task"
    assert metadata["no_real_codex_started"] is False
    assert metadata["sandbox_test_status"] == "SUCCEEDED"
    assert metadata["changed_files"] == ALLOWED_FILES
    assert metadata["policy_violations"] == []
    assert all(artifact["uri"].startswith("artifact://codex/") for artifact in output["artifacts"])
    assert _git(repo_path, "status", "--short") == before_status
    assert "coding_worker.completed" in [
        event.event_type for event in service.repo.list_audit_events(project.project_id)
    ]


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
