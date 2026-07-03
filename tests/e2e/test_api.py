from __future__ import annotations

import subprocess
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_org.adapters.api.main import AppContainer, create_app
from ai_org.adapters.codex.clients import MockCodexClient
from ai_org.adapters.codex.worker import CodexWorker
from ai_org.adapters.memory.repositories import InMemoryRepository
from ai_org.adapters.workers.mock import DefaultWorkerRegistry, MockReviewWorker
from ai_org.application.merge_approval import (
    InMemoryMergeCandidateStore,
    InMemoryPatchArtifactStore,
    MergeApprovalService,
    MergeService,
)
from ai_org.application.service import ProjectApplicationService
from ai_org.domain.enums import WorkerType
from ai_org.orchestration.workflow import LangGraphWorkflow


def test_fastapi_low_risk_end_to_end() -> None:
    client = TestClient(create_app())

    assert client.get("/health").json()["status"] == "ok"
    created = client.post("/projects", json={"title": "API", "goal": "Run"}).json()
    project_id = created["project_id"]

    run = client.post(f"/projects/{project_id}/run")
    assert run.status_code == 200
    assert run.json()["project"]["status"] == "COMPLETED"
    assert client.get(f"/projects/{project_id}/tasks").json()[0]["status"] == "ACCEPTED"
    assert client.get(f"/projects/{project_id}/audit-events").json()


def test_fastapi_high_risk_approval_end_to_end() -> None:
    client = TestClient(create_app())
    created = client.post(
        "/projects",
        json={
            "title": "Risk",
            "goal": "Needs approval",
            "tasks": [{"title": "Risky", "objective": "x", "risk_level": "HIGH"}],
        },
    ).json()
    project_id = created["project_id"]

    waiting = client.post(f"/projects/{project_id}/run").json()
    approval_id = waiting["approvals"][0]["approval_id"]
    assert waiting["project"]["status"] == "WAITING_APPROVAL"

    approved = client.post(
        f"/approvals/{approval_id}/decision",
        json={"decision": "APPROVED", "decision_reason": "ok"},
    )
    assert approved.status_code == 200
    assert approved.json()["project"]["status"] == "COMPLETED"


def test_fastapi_errors_are_standardized_and_redacted() -> None:
    client = TestClient(create_app())

    missing = client.get("/projects/missing")
    assert missing.status_code == 404
    body = missing.json()
    assert set(body) == {"code", "message", "request_id"}
    assert "Traceback" not in str(body)

    invalid = client.post("/projects", json={"title": "x"})
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "VALIDATION_ERROR"


def test_fastapi_exposes_worker_runs_and_artifact_metadata(tmp_path: Path) -> None:
    client = TestClient(_codex_app(tmp_path))
    created = client.post(
        "/projects",
        json={
            "title": "Codex API",
            "goal": "Query worker run artifacts",
            "tasks": [
                {
                    "title": "Code",
                    "objective": "Create a deterministic artifact",
                    "worker_type": "codex",
                    "metadata": {
                        "codex_mode": "mock",
                        "mock_output_file": "src/generated.txt",
                        "allowed_files": ["src/generated.txt"],
                    },
                }
            ],
        },
    ).json()
    project_id = created["project_id"]

    run = client.post(f"/projects/{project_id}/run")
    assert run.status_code == 200
    runs = client.get(f"/projects/{project_id}/worker-runs")
    assert runs.status_code == 200
    production = [item for item in runs.json() if item["worker_type"] == "codex"]
    assert len(production) == 1

    run_id = production[0]["run_id"]
    assert client.get(f"/worker-runs/{run_id}").json()["run_id"] == run_id
    artifacts = client.get(f"/worker-runs/{run_id}/artifacts")
    assert artifacts.status_code == 200
    assert {artifact["name"] for artifact in artifacts.json()} == {
        "codex-prompt",
        "codex-command-log",
        "codex-diff",
    }

    missing = client.get("/worker-runs/missing/artifacts")
    assert missing.status_code == 404


def _codex_app(tmp_path: Path) -> FastAPI:
    repo_path = _git_repo(tmp_path / "repo")
    repo = InMemoryRepository()
    registry = DefaultWorkerRegistry(
        workers={WorkerType.CODEX.value: CodexWorker(repo_path, client=MockCodexClient())},
        review_worker=MockReviewWorker(),
    )
    service = ProjectApplicationService(repo, registry)
    workflow = LangGraphWorkflow(service)
    candidate_store = InMemoryMergeCandidateStore()
    patch_store = InMemoryPatchArtifactStore()
    merge_approval_service = MergeApprovalService(candidate_store, repo.add_audit_event)
    merge_service = MergeService(merge_approval_service, patch_store, repo.add_audit_event)
    return create_app(
        AppContainer(
            repo=repo,
            service=service,
            workflow=workflow,
            storage_backend="memory",
            close_callback=lambda: None,
            merge_approval_service=merge_approval_service,
            merge_service=merge_service,
            patch_artifact_store=patch_store,
        )
    )


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
