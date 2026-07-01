from __future__ import annotations

import pytest
from pydantic import ValidationError

from ai_org.domain.enums import AgentResultStatus
from ai_org.protocols.schemas import (
    AgentResult,
    Artifact,
    CreateProjectRequest,
    TaskSpec,
    WorkerTestRecord,
)


def test_create_project_request_validates_task_specs() -> None:
    request = CreateProjectRequest(
        title="Build",
        goal="Create skeleton",
        tasks=[
            TaskSpec(
                title="Research",
                objective="Collect facts",
                metadata={"allowed_files": ["docs/**"]},
            )
        ],
    )

    assert request.tasks[0].worker_type == "research"
    assert request.tasks[0].risk_level == "LOW"
    assert request.tasks[0].metadata["allowed_files"] == ["docs/**"]


def test_protocols_reject_extra_fields_and_free_text_worker_result() -> None:
    with pytest.raises(ValidationError):
        CreateProjectRequest(title="x", goal="y", unexpected=True)  # type: ignore[call-arg]

    with pytest.raises(ValidationError):
        AgentResult.model_validate("just text")


def test_agent_result_is_structured() -> None:
    result = AgentResult(
        task_id="task_1",
        status=AgentResultStatus.SUCCEEDED,
        summary="done",
        artifacts=[Artifact(name="a", uri="memory://a")],
        evidence=["e"],
        tests_run=[WorkerTestRecord(name="t", status="passed")],
        assumptions=[],
        risks=[],
        unresolved_questions=[],
        metadata={"safe": True},
    )

    dumped = result.model_dump()
    assert dumped["summary"] == "done"
    assert isinstance(dumped["artifacts"], list)
