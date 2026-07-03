from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_org.adapters.api.main import AppContainer, create_app
from ai_org.domain.merge_candidate import MergeCandidate, MergeCandidateSourceType


def test_merge_candidate_api_lists_and_reads_without_raw_diff_or_local_paths() -> None:
    app = create_app()
    client = TestClient(app)
    container = _container(app)
    project_id, task_id = _project_and_task(client)
    candidate_id = _candidate(container, project_id, task_id)

    detail = client.get(f"/merge-candidates/{candidate_id}")
    listing = client.get(f"/projects/{project_id}/merge-candidates")

    assert detail.status_code == 200
    assert listing.status_code == 200
    body = detail.json()
    assert body["candidate_id"] == candidate_id
    assert body["status"] == "WAITING_APPROVAL"
    assert "raw_diff" not in body
    assert "C:\\Users" not in str(body)
    assert "/home/" not in str(body)
    assert listing.json()[0]["patch_artifact_uri"].startswith("artifact://")


def test_merge_candidate_api_returns_404_and_409_for_missing_or_illegal_states() -> None:
    app = create_app()
    client = TestClient(app)
    container = _container(app)
    project_id, task_id = _project_and_task(client)
    candidate_id = _candidate(container, project_id, task_id)

    assert client.get("/merge-candidates/missing").status_code == 404

    unapproved_merge = client.post(f"/merge-candidates/{candidate_id}/merge", json={})
    assert unapproved_merge.status_code == 409

    approval = client.post(
        f"/merge-candidates/{candidate_id}/approval",
        json={"decision": "APPROVED", "decided_by": "reviewer", "reason": "safe"},
    )
    assert approval.status_code == 200
    assert approval.json()["status"] == "APPROVED"

    duplicate_approval = client.post(
        f"/merge-candidates/{candidate_id}/approval",
        json={"decision": "APPROVED", "decided_by": "reviewer", "reason": "duplicate"},
    )
    assert duplicate_approval.status_code == 409

    unconfigured_merge = client.post(f"/merge-candidates/{candidate_id}/merge", json={})
    assert unconfigured_merge.status_code == 409


def test_merge_candidate_api_rejects_waiting_candidate() -> None:
    app = create_app()
    client = TestClient(app)
    container = _container(app)
    project_id, task_id = _project_and_task(client)
    candidate_id = _candidate(container, project_id, task_id)

    response = client.post(
        f"/merge-candidates/{candidate_id}/approval",
        json={"decision": "REJECTED", "decided_by": "reviewer", "reason": "unsafe"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert client.post(f"/merge-candidates/{candidate_id}/merge", json={}).status_code == 409


def test_merge_candidate_api_redacts_malformed_internal_candidate_fields() -> None:
    app = create_app()
    client = TestClient(app)
    container = _container(app)
    project_id, task_id = _project_and_task(client)
    candidate = MergeCandidate(
        candidate_id="mc-malformed",
        project_id=project_id,
        task_id=task_id,
        worker_run_id="run-malformed",
        source_type=MergeCandidateSourceType.MANUAL_FIXTURE,
        base_commit="abc123",
        changed_files=["C:\\Users\\11566\\repo\\.envrc"],
        diff_summary="C:\\Users\\11566\\repo\\patch.diff",
        patch_artifact_uri="artifact://C:\\Users\\11566\\repo\\TOKEN.patch",
        tests_summary="TOKEN",
        review_decision="ACCEPTED",
        candidate_branch="TOKEN",
        worktree_uri="C:\\Users\\11566\\repo",
    )
    container.merge_approval_service.store.add_candidate(candidate)

    response = client.get("/merge-candidates/mc-malformed")

    assert response.status_code == 200
    body = str(response.json())
    assert "C:\\Users" not in body
    assert "TOKEN" not in body


def _project_and_task(client: TestClient) -> tuple[str, str]:
    created = client.post("/projects", json={"title": "Merge API", "goal": "Review"}).json()
    tasks = client.get(f"/projects/{created['project_id']}/tasks").json()
    return created["project_id"], tasks[0]["task_id"]


def _candidate(container: AppContainer, project_id: str, task_id: str) -> str:
    uri = f"artifact://merge-candidates/{task_id}.patch"
    container.patch_artifact_store.add_patch(
        uri,
        "diff --git a/README.md b/README.md\n--- a/README.md\n+++ b/README.md\n",
    )
    candidate = container.merge_approval_service.create_candidate(
        project_id=project_id,
        task_id=task_id,
        worker_run_id=f"run-{task_id}",
        source_type=MergeCandidateSourceType.MANUAL_FIXTURE,
        base_commit="abc123",
        changed_files=["README.md"],
        diff_summary="README summary only",
        patch_artifact_uri=uri,
        tests_summary="fixture",
        review_decision="accepted",
        worktree_uri="worktree://fixture/api",
    )
    return candidate.candidate_id


def _container(app: FastAPI) -> AppContainer:
    container = app.state.container
    assert isinstance(container, AppContainer)
    return container
