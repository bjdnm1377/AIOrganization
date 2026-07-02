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

pytestmark = pytest.mark.manual_codex_multi_file_task

ALLOWED_FILES = [
    "docs/MERGE_APPROVAL.md",
    "src/ai_org/adapters/codex/merge_candidate.py",
    "tests/unit/test_codex_merge_candidate.py",
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
    os.environ.get("AI_ORG_ENABLE_REAL_CODEX_MULTI_FILE_TASK", "").lower() != "true",
    reason="real Codex CLI multi-file task test requires explicit opt-in",
)
@pytest.mark.skipif(shutil.which("codex") is None, reason="Codex CLI is not installed")
@pytest.mark.skipif(not _docker_available(), reason="Docker is not available")
def test_real_codex_multi_file_task_creates_merge_candidate_for_human_approval() -> None:
    repo_path = Path(__file__).resolve().parents[2]
    before_status = _git(repo_path, "status", "--short")
    repo = InMemoryRepository()
    registry = DefaultWorkerRegistry(
        workers={
            WorkerType.CODEX.value: CodexWorker(
                repo_path,
                client=LocalCodexCliClient(timeout_seconds=600),
                sandbox_runner=DockerSandboxRunner(),
            ),
        },
        review_worker=MockReviewWorker(),
    )
    service = ProjectApplicationService(repo, registry)
    workflow = LangGraphWorkflow(service)
    project = service.create_project(
        CreateProjectRequest(
            title="Real Codex multi-file merge candidate task",
            goal="Verify controlled Codex multi-file task and pending merge candidate",
            tasks=[
                TaskSpec(
                    title="Update MergeCandidate summary path",
                    objective=(
                        "Modify exactly these three files and no other files: "
                        "docs/MERGE_APPROVAL.md, "
                        "src/ai_org/adapters/codex/merge_candidate.py, "
                        "tests/unit/test_codex_merge_candidate.py. "
                        "If any file is absent in the task worktree, create it instead of "
                        "trying to update a missing file. "
                        "Make a minimal marker-only multi-file change: add "
                        "MERGE_CANDIDATE_MANUAL_TASK_MARKER = 'human-approval-only' "
                        "to the module, add or update one unit test that imports that "
                        "constant and asserts it equals 'human-approval-only', and add "
                        "one documentation sentence containing 'human-approval-only'. "
                        "Do not rewrite unrelated logic. Keep build_merge_candidate_summary "
                        "side-effect-free: no file I/O, no shell, no network, no environment "
                        "reads. Preserve merge_performed=False, auto_merge=False, "
                        "auto_push=False, human_approval_required=True, and "
                        "approval_state='waiting_merge_approval'."
                    ),
                    worker_type=WorkerType.CODEX,
                    max_attempts=1,
                    metadata={
                        "codex_mode": "local_multi_file_task",
                        "codex_sandbox": "workspace-write",
                        "codex_approval_policy": "on-request",
                        "sandbox_test_profile": "real_multi_file_task_merge_candidate",
                    },
                    acceptance_criteria=["real codex multi-file task reviewed independently"],
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
    assert metadata["codex_mode"] == "local_multi_file_task"
    assert metadata["no_real_codex_started"] is False
    assert metadata["sandbox_test_status"] == "SUCCEEDED"
    assert metadata["changed_files"] == ALLOWED_FILES
    assert metadata["policy_violations"] == []
    assert metadata["merge_candidate_status"] == "WAITING_MERGE_APPROVAL"
    candidate = metadata["merge_candidate"]
    assert candidate["changed_files"] == ALLOWED_FILES
    assert candidate["merge_performed"] is False
    assert candidate["auto_merge"] is False
    assert candidate["auto_push"] is False
    assert candidate["human_approval_required"] is True
    assert candidate["approval_state"] == "waiting_merge_approval"
    assert metadata["merge_candidate_artifact_uri"].startswith("artifact://codex/")
    assert all(artifact["uri"].startswith("artifact://codex/") for artifact in output["artifacts"])
    assert _git(repo_path, "status", "--short") == before_status
    audit_events = [
        event.event_type for event in service.repo.list_audit_events(project.project_id)
    ]
    assert "coding_worker.completed" in audit_events
    assert "merge_candidate.created" in audit_events


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
