from __future__ import annotations

from fastapi.testclient import TestClient

from ai_org.adapters.api.main import create_app


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
