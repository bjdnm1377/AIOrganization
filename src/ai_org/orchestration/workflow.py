from __future__ import annotations

from typing import Any, Literal, TypedDict, cast

from ai_org.application.service import ProjectApplicationService
from ai_org.domain.enums import ApprovalStatus
from ai_org.orchestration.checkpoint_security import (
    assert_checkpoint_security,
    assert_state_is_safe,
    build_serializer,
    configure_checkpoint_security,
)
from ai_org.protocols.schemas import AgentResult, ApprovalDecision, ReviewReport, WorkflowStatus

configure_checkpoint_security()

from langgraph.checkpoint.memory import InMemorySaver  # noqa: E402
from langgraph.graph import END, START, StateGraph  # noqa: E402
from langgraph.types import Command, interrupt  # noqa: E402


class WorkflowState(TypedDict, total=False):
    project_id: str
    selected_task_id: str | None
    needs_approval: bool
    approval_id: str | None
    approval_decision: str | None
    agent_result: dict[str, Any] | None
    review_report: dict[str, Any] | None
    review_outcome: str | None


class LangGraphWorkflow:
    def __init__(self, service: ProjectApplicationService, checkpointer: Any | None = None) -> None:
        assert_checkpoint_security()
        self.service = service
        self.checkpointer = checkpointer or InMemorySaver(serde=build_serializer())
        self.graph: Any = self._build_graph().compile(checkpointer=cast(Any, self.checkpointer))

    def run(self, project_id: str) -> WorkflowStatus:
        state: WorkflowState = {"project_id": project_id}
        assert_state_is_safe(state)
        self.graph.invoke(state, config=self._config(project_id))
        return self.service.get_status(project_id)

    def resume(
        self, project_id: str, approval_id: str, decision: ApprovalDecision
    ) -> WorkflowStatus:
        resume_payload = {
            "approval_id": approval_id,
            "decision": decision.model_dump(mode="json"),
        }
        assert_state_is_safe(resume_payload)
        self.graph.invoke(Command(resume=resume_payload), config=self._config(project_id))
        return self.service.get_status(project_id)

    def _build_graph(self) -> Any:
        builder = StateGraph(WorkflowState)
        builder.add_node("initialize_project", self._initialize_project)
        builder.add_node("select_ready_task", self._select_ready_task)
        builder.add_node("evaluate_risk", self._evaluate_risk)
        builder.add_node("request_approval", self._request_approval)
        builder.add_node("dispatch_worker", self._dispatch_worker)
        builder.add_node("persist_worker_result", self._persist_worker_result)
        builder.add_node("deterministic_validation", self._deterministic_validation)
        builder.add_node("review_result", self._review_result)
        builder.add_node("handle_review_decision", self._handle_review_decision)
        builder.add_node("finalize_project", self._finalize_project)

        builder.add_edge(START, "initialize_project")
        builder.add_edge("initialize_project", "select_ready_task")
        builder.add_conditional_edges(
            "select_ready_task",
            self._route_after_select,
            {"evaluate_risk": "evaluate_risk", "finalize_project": "finalize_project"},
        )
        builder.add_conditional_edges(
            "evaluate_risk",
            self._route_after_risk,
            {"request_approval": "request_approval", "dispatch_worker": "dispatch_worker"},
        )
        builder.add_conditional_edges(
            "request_approval",
            self._route_after_approval,
            {"dispatch_worker": "dispatch_worker", "finalize_project": "finalize_project"},
        )
        builder.add_edge("dispatch_worker", "persist_worker_result")
        builder.add_edge("persist_worker_result", "deterministic_validation")
        builder.add_edge("deterministic_validation", "review_result")
        builder.add_edge("review_result", "handle_review_decision")
        builder.add_conditional_edges(
            "handle_review_decision",
            self._route_after_review,
            {"select_ready_task": "select_ready_task", "finalize_project": "finalize_project"},
        )
        builder.add_edge("finalize_project", END)
        return builder

    def _initialize_project(self, state: WorkflowState) -> WorkflowState:
        self.service.mark_project_running(state["project_id"])
        return state

    def _select_ready_task(self, state: WorkflowState) -> WorkflowState:
        task = self.service.select_ready_task(state["project_id"])
        return {**state, "selected_task_id": task.task_id if task else None}

    def _evaluate_risk(self, state: WorkflowState) -> WorkflowState:
        task_id = _require_selected_task(state)
        return {**state, "needs_approval": self.service.task_requires_approval(task_id)}

    def _request_approval(self, state: WorkflowState) -> WorkflowState:
        task_id = _require_selected_task(state)
        approval = self.service.request_approval(task_id)
        resume_payload = interrupt(
            {
                "approval_id": approval.approval_id,
                "project_id": approval.project_id,
                "task_id": approval.task_id,
                "risk_level": approval.risk_level.value,
            }
        )
        decision = ApprovalDecision.model_validate(resume_payload["decision"])
        if resume_payload["approval_id"] != approval.approval_id:
            raise ValueError("Approval resume payload does not match interrupted approval")
        updated = self.service.apply_approval_decision(approval.approval_id, decision)
        return {
            **state,
            "approval_id": approval.approval_id,
            "approval_decision": updated.status.value,
        }

    def _dispatch_worker(self, state: WorkflowState) -> WorkflowState:
        result = self.service.dispatch_worker(_require_selected_task(state))
        return {**state, "agent_result": result.model_dump(mode="json")}

    def _persist_worker_result(self, state: WorkflowState) -> WorkflowState:
        # Worker results are persisted by ProjectApplicationService.complete_worker_run.
        return state

    def _deterministic_validation(self, state: WorkflowState) -> WorkflowState:
        result = AgentResult.model_validate(state["agent_result"])
        self.service.deterministic_validation(result)
        return state

    def _review_result(self, state: WorkflowState) -> WorkflowState:
        result = AgentResult.model_validate(state["agent_result"])
        report = self.service.review_result(_require_selected_task(state), result)
        return {**state, "review_report": report.model_dump(mode="json")}

    def _handle_review_decision(self, state: WorkflowState) -> WorkflowState:
        report = ReviewReport.model_validate(state["review_report"])
        outcome = self.service.handle_review_decision(_require_selected_task(state), report)
        return {**state, "review_outcome": outcome}

    def _finalize_project(self, state: WorkflowState) -> WorkflowState:
        self.service.finalize_project(state["project_id"])
        return state

    def _route_after_select(
        self, state: WorkflowState
    ) -> Literal["evaluate_risk", "finalize_project"]:
        return "evaluate_risk" if state.get("selected_task_id") else "finalize_project"

    def _route_after_risk(
        self, state: WorkflowState
    ) -> Literal["request_approval", "dispatch_worker"]:
        return "request_approval" if state.get("needs_approval") else "dispatch_worker"

    def _route_after_approval(
        self, state: WorkflowState
    ) -> Literal["dispatch_worker", "finalize_project"]:
        return (
            "dispatch_worker"
            if state.get("approval_decision") == ApprovalStatus.APPROVED.value
            else "finalize_project"
        )

    def _route_after_review(
        self, state: WorkflowState
    ) -> Literal["select_ready_task", "finalize_project"]:
        return (
            "select_ready_task" if state.get("review_outcome") == "rework" else "finalize_project"
        )

    def _config(self, project_id: str) -> Any:
        return {"configurable": {"thread_id": project_id}}


def _require_selected_task(state: WorkflowState) -> str:
    task_id = state.get("selected_task_id")
    if not task_id:
        raise ValueError("No selected task in workflow state")
    return task_id
