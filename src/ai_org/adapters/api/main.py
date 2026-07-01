from __future__ import annotations

import os
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from ai_org.adapters.memory.repositories import InMemoryRepository
from ai_org.adapters.postgres.repositories import SqlAlchemyRepository
from ai_org.adapters.postgres.session import (
    build_engine,
    build_session_factory,
    configure_search_path,
)
from ai_org.adapters.workers.mock import DefaultWorkerRegistry
from ai_org.application.mappers import (
    approval_to_response,
    audit_event_to_response,
    task_to_response,
    worker_run_to_response,
)
from ai_org.application.service import ProjectApplicationService
from ai_org.domain.errors import ConflictError, DomainError, InvalidTransitionError, NotFoundError
from ai_org.orchestration.checkpoint_security import assert_checkpoint_security
from ai_org.orchestration.postgres_checkpoint import postgres_checkpointer
from ai_org.orchestration.workflow import LangGraphWorkflow
from ai_org.ports.repositories import Repository
from ai_org.protocols.schemas import (
    AgentResult,
    ApprovalDecision,
    ApprovalResponse,
    Artifact,
    AuditEventResponse,
    CreateProjectRequest,
    ErrorResponse,
    ProjectResponse,
    TaskResponse,
    WorkerRunResponse,
    WorkflowStatus,
)


@dataclass(slots=True)
class AppContainer:
    repo: Repository
    service: ProjectApplicationService
    workflow: LangGraphWorkflow
    storage_backend: str
    close_callback: Callable[[], None]

    def close(self) -> None:
        self.close_callback()


def build_container(database_url: str | None = None) -> AppContainer:
    database_url = database_url or os.environ.get("AI_ORG_DATABASE_URL")
    if database_url:
        return _build_postgres_container(database_url)

    repo = InMemoryRepository()
    service = ProjectApplicationService(repo, DefaultWorkerRegistry.create())
    workflow = LangGraphWorkflow(service)
    return AppContainer(
        repo=repo,
        service=service,
        workflow=workflow,
        storage_backend="memory",
        close_callback=_noop,
    )


def create_app(container: AppContainer | None = None) -> FastAPI:
    assert_checkpoint_security()
    active = container or build_container()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            active.close()

    app = FastAPI(title="AI Organization", version="0.1.0", lifespan=lifespan)
    app.state.container = active

    @app.exception_handler(NotFoundError)
    async def not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
        return _error("NOT_FOUND", str(exc), 404)

    async def conflict_handler(request: Request, exc: Exception) -> JSONResponse:
        message = str(exc) if isinstance(exc, DomainError) else "Conflict"
        return _error("CONFLICT", message, 409)

    app.add_exception_handler(ConflictError, conflict_handler)
    app.add_exception_handler(InvalidTransitionError, conflict_handler)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        return _error("VALIDATION_ERROR", "Request validation failed", 422)

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        return _error("INTERNAL_ERROR", "Internal server error", 500)

    @app.get("/health")
    def health() -> dict[str, object]:
        return {
            "status": "ok",
            "checkpoint_strict_msgpack": True,
            "storage_backend": active.storage_backend,
        }

    @app.post("/projects", response_model=ProjectResponse)
    def create_project(request: CreateProjectRequest) -> ProjectResponse:
        return active.service.create_project(request)

    @app.get("/projects/{project_id}", response_model=ProjectResponse)
    def get_project(project_id: str) -> ProjectResponse:
        return active.service.get_project(project_id)

    @app.get("/projects/{project_id}/tasks", response_model=list[TaskResponse])
    def list_tasks(project_id: str) -> list[TaskResponse]:
        active.service.get_project(project_id)
        return [task_to_response(task) for task in active.repo.list_tasks(project_id)]

    @app.get("/projects/{project_id}/worker-runs", response_model=list[WorkerRunResponse])
    def list_project_worker_runs(project_id: str) -> list[WorkerRunResponse]:
        active.service.get_project(project_id)
        tasks = active.repo.list_tasks(project_id)
        runs = [run for task in tasks for run in active.repo.list_worker_runs(task.task_id)]
        return [worker_run_to_response(run) for run in runs]

    @app.get("/tasks/{task_id}/worker-runs", response_model=list[WorkerRunResponse])
    def list_task_worker_runs(task_id: str) -> list[WorkerRunResponse]:
        if active.repo.get_task(task_id) is None:
            raise NotFoundError(f"Task {task_id} not found")
        return [worker_run_to_response(run) for run in active.repo.list_worker_runs(task_id)]

    @app.get("/worker-runs/{run_id}", response_model=WorkerRunResponse)
    def get_worker_run(run_id: str) -> WorkerRunResponse:
        run = active.repo.get_worker_run(run_id)
        if run is None:
            raise NotFoundError(f"WorkerRun {run_id} not found")
        return worker_run_to_response(run)

    @app.get("/worker-runs/{run_id}/artifacts", response_model=list[Artifact])
    def list_worker_run_artifacts(run_id: str) -> list[Artifact]:
        run = active.repo.get_worker_run(run_id)
        if run is None:
            raise NotFoundError(f"WorkerRun {run_id} not found")
        if not run.structured_output:
            return []
        try:
            result = AgentResult.model_validate(run.structured_output)
        except ValidationError:
            return []
        return result.artifacts

    @app.post("/projects/{project_id}/run", response_model=WorkflowStatus)
    def run_project(project_id: str) -> WorkflowStatus:
        active.service.get_project(project_id)
        return active.workflow.run(project_id)

    @app.get("/projects/{project_id}/status", response_model=WorkflowStatus)
    def get_project_status(project_id: str) -> WorkflowStatus:
        return active.service.get_status(project_id)

    @app.get("/projects/{project_id}/approvals", response_model=list[ApprovalResponse])
    def list_approvals(project_id: str) -> list[ApprovalResponse]:
        active.service.get_project(project_id)
        return [
            approval_to_response(approval) for approval in active.repo.list_approvals(project_id)
        ]

    @app.post("/approvals/{approval_id}/decision", response_model=WorkflowStatus)
    def decide_approval(approval_id: str, decision: ApprovalDecision) -> WorkflowStatus:
        approval = active.repo.get_approval(approval_id)
        if approval is None:
            raise NotFoundError(f"Approval {approval_id} not found")
        return active.workflow.resume(approval.project_id, approval_id, decision)

    @app.get("/projects/{project_id}/audit-events", response_model=list[AuditEventResponse])
    def list_audit_events(project_id: str) -> list[AuditEventResponse]:
        active.service.get_project(project_id)
        return [
            audit_event_to_response(event) for event in active.repo.list_audit_events(project_id)
        ]

    return app


def _error(code: str, message: str, status_code: int) -> JSONResponse:
    payload = ErrorResponse(code=code, message=message, request_id=f"req_{uuid4().hex}")
    return JSONResponse(status_code=status_code, content=payload.model_dump(mode="json"))


def _build_postgres_container(database_url: str) -> AppContainer:
    engine = build_engine(database_url)
    session_factory = build_session_factory(engine)
    session = session_factory()
    configure_search_path(session)
    repo = SqlAlchemyRepository(session)
    service = ProjectApplicationService(
        repo,
        DefaultWorkerRegistry.create(),
        commit=session.commit,
        rollback=session.rollback,
    )
    checkpoint_url = os.environ.get("AI_ORG_CHECKPOINT_DATABASE_URL") or _psycopg_url(database_url)
    setup_checkpoint = os.environ.get("AI_ORG_CHECKPOINT_SETUP", "false").lower() == "true"
    checkpoint_context = postgres_checkpointer(checkpoint_url, setup=setup_checkpoint)
    checkpointer = checkpoint_context.__enter__()
    workflow = LangGraphWorkflow(service, checkpointer=checkpointer)

    def close() -> None:
        checkpoint_context.__exit__(None, None, None)
        session.close()
        engine.dispose()

    return AppContainer(
        repo=repo,
        service=service,
        workflow=workflow,
        storage_backend="postgres",
        close_callback=close,
    )


def _psycopg_url(database_url: str) -> str:
    return database_url.replace("postgresql+psycopg://", "postgresql://", 1)


def _noop() -> None:
    return None


app = create_app()
