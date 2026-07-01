from __future__ import annotations

import pytest

from ai_org.application.service import ProjectApplicationService
from ai_org.domain.enums import (
    ProjectStatus,
    RiskLevel,
    TaskStatus,
    WorkerRunStatus,
    WorkerType,
)
from ai_org.domain.errors import ConflictError
from ai_org.domain.models import WorkerRun, utc_now
from ai_org.orchestration.workflow import LangGraphWorkflow
from ai_org.protocols.schemas import ApprovalDecision, CreateProjectRequest, TaskSpec


def test_scenario_a_low_risk_auto_completes(
    service: ProjectApplicationService, workflow: LangGraphWorkflow
) -> None:
    project = service.create_project(CreateProjectRequest(title="Low", goal="Complete low risk"))

    status = workflow.run(project.project_id)

    assert status.project.status == ProjectStatus.COMPLETED
    assert [task.status for task in status.tasks] == [TaskStatus.ACCEPTED]
    assert len(status.worker_runs) == 2
    assert [event.event_type for event in service.repo.list_audit_events(project.project_id)] == [
        "project.created",
        "workflow.running",
        "worker.dispatched",
        "worker.completed",
        "review.completed",
        "task.accepted",
        "project.completed",
    ]


def test_scenario_b_high_risk_interrupt_and_resume_with_recreated_workflow(
    service: ProjectApplicationService, workflow: LangGraphWorkflow
) -> None:
    project = service.create_project(
        CreateProjectRequest(
            title="High",
            goal="Needs approval",
            tasks=[
                TaskSpec(
                    title="Risky",
                    objective="Do high risk work",
                    worker_type=WorkerType.RESEARCH,
                    risk_level=RiskLevel.HIGH,
                )
            ],
        )
    )

    waiting = workflow.run(project.project_id)
    assert waiting.project.status == ProjectStatus.WAITING_APPROVAL
    assert waiting.tasks[0].status == TaskStatus.WAITING_APPROVAL
    assert len(waiting.approvals) == 1
    assert waiting.worker_runs == []

    recreated = LangGraphWorkflow(service, checkpointer=workflow.checkpointer)
    completed = recreated.resume(
        project.project_id,
        waiting.approvals[0].approval_id,
        ApprovalDecision(decision="APPROVED", decision_reason="approved in test"),
    )

    assert completed.project.status == ProjectStatus.COMPLETED
    assert completed.tasks[0].status == TaskStatus.ACCEPTED
    assert len([run for run in completed.worker_runs if run.worker_type != "review"]) == 1


def test_scenario_c_approval_rejection_blocks_without_worker(
    service: ProjectApplicationService, workflow: LangGraphWorkflow
) -> None:
    project = service.create_project(
        CreateProjectRequest(
            title="Reject",
            goal="Reject approval",
            tasks=[TaskSpec(title="Risky", objective="x", risk_level=RiskLevel.HIGH)],
        )
    )

    waiting = workflow.run(project.project_id)
    blocked = workflow.resume(
        project.project_id,
        waiting.approvals[0].approval_id,
        ApprovalDecision(decision="REJECTED", decision_reason="not allowed"),
    )

    assert blocked.project.status == ProjectStatus.BLOCKED
    assert blocked.tasks[0].status == TaskStatus.BLOCKED
    assert blocked.worker_runs == []


def test_scenario_d_rework_stops_at_max_attempts(
    service: ProjectApplicationService, workflow: LangGraphWorkflow
) -> None:
    project = service.create_project(
        CreateProjectRequest(
            title="Rework",
            goal="Stop after rework",
            tasks=[
                TaskSpec(
                    title="Always rework",
                    objective="Trigger deterministic rework",
                    acceptance_criteria=["force_rework"],
                    max_attempts=2,
                )
            ],
        )
    )

    status = workflow.run(project.project_id)

    assert status.project.status == ProjectStatus.BLOCKED
    assert status.tasks[0].status == TaskStatus.BLOCKED
    assert status.tasks[0].attempt_count == 2
    assert len(status.worker_runs) == 4


def test_scenario_e_repeated_run_is_idempotent(
    service: ProjectApplicationService, workflow: LangGraphWorkflow
) -> None:
    project = service.create_project(CreateProjectRequest(title="Idem", goal="Repeat"))

    first = workflow.run(project.project_id)
    second = workflow.run(project.project_id)

    assert first.project.status == second.project.status == ProjectStatus.COMPLETED
    assert len(first.worker_runs) == len(second.worker_runs) == 2


def test_existing_running_worker_run_is_not_executed_again(
    service: ProjectApplicationService,
) -> None:
    project = service.create_project(CreateProjectRequest(title="Crash", goal="No duplicate"))
    task = service.repo.list_tasks(project.project_id)[0]
    service.repo.add_worker_run(
        WorkerRun(
            run_id="run_existing",
            task_id=task.task_id,
            worker_type=task.worker_type,
            status=WorkerRunStatus.RUNNING,
            structured_input={"objective": task.objective},
            structured_output=None,
            attempt_number=1,
            idempotency_key=f"worker:{task.task_id}:1:produce",
            started_at=utc_now(),
        )
    )

    with pytest.raises(ConflictError):
        service.dispatch_worker(task.task_id)

    runs = service.repo.list_worker_runs(task.task_id)
    assert len(runs) == 1
    assert runs[0].run_id == "run_existing"
