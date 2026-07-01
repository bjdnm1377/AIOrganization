from __future__ import annotations

from copy import deepcopy
from threading import RLock

from ai_org.domain.errors import ConflictError
from ai_org.domain.models import Approval, AuditEvent, Project, Task, WorkerRun
from ai_org.ports.repositories import Repository


class InMemoryRepository(Repository):
    def __init__(self) -> None:
        self._lock = RLock()
        self._projects: dict[str, Project] = {}
        self._project_idempotency: dict[str, str] = {}
        self._tasks: dict[str, Task] = {}
        self._worker_runs: dict[str, WorkerRun] = {}
        self._worker_run_idempotency: dict[str, str] = {}
        self._approvals: dict[str, Approval] = {}
        self._approval_idempotency: dict[str, str] = {}
        self._audit_events: list[AuditEvent] = []

    def add_project(self, project: Project) -> None:
        with self._lock:
            if project.project_id in self._projects:
                raise ConflictError(f"Project {project.project_id} already exists")
            if project.idempotency_key:
                existing = self._project_idempotency.get(project.idempotency_key)
                if existing is not None:
                    raise ConflictError(f"Project idempotency key already used: {existing}")
                self._project_idempotency[project.idempotency_key] = project.project_id
            self._projects[project.project_id] = deepcopy(project)

    def get_project(self, project_id: str) -> Project | None:
        with self._lock:
            project = self._projects.get(project_id)
            return deepcopy(project) if project else None

    def get_project_by_idempotency_key(self, key: str) -> Project | None:
        with self._lock:
            project_id = self._project_idempotency.get(key)
            return self.get_project(project_id) if project_id else None

    def update_project(self, project: Project, expected_version: int) -> None:
        with self._lock:
            current = self._projects.get(project.project_id)
            if current is None or current.version != expected_version:
                raise ConflictError("Project optimistic lock conflict")
            updated = deepcopy(project)
            updated.version = expected_version + 1
            self._projects[project.project_id] = updated

    def add_task(self, task: Task) -> None:
        with self._lock:
            if task.task_id in self._tasks:
                raise ConflictError(f"Task {task.task_id} already exists")
            self._tasks[task.task_id] = deepcopy(task)

    def get_task(self, task_id: str) -> Task | None:
        with self._lock:
            task = self._tasks.get(task_id)
            return deepcopy(task) if task else None

    def list_tasks(self, project_id: str) -> list[Task]:
        with self._lock:
            return [
                deepcopy(task) for task in self._tasks.values() if task.project_id == project_id
            ]

    def update_task(self, task: Task, expected_version: int) -> None:
        with self._lock:
            current = self._tasks.get(task.task_id)
            if current is None or current.version != expected_version:
                raise ConflictError("Task optimistic lock conflict")
            updated = deepcopy(task)
            updated.version = expected_version + 1
            self._tasks[task.task_id] = updated

    def add_worker_run(self, worker_run: WorkerRun) -> WorkerRun:
        with self._lock:
            existing_id = self._worker_run_idempotency.get(worker_run.idempotency_key)
            if existing_id:
                return deepcopy(self._worker_runs[existing_id])
            if worker_run.run_id in self._worker_runs:
                raise ConflictError(f"WorkerRun {worker_run.run_id} already exists")
            self._worker_runs[worker_run.run_id] = deepcopy(worker_run)
            self._worker_run_idempotency[worker_run.idempotency_key] = worker_run.run_id
            return deepcopy(worker_run)

    def get_worker_run(self, run_id: str) -> WorkerRun | None:
        with self._lock:
            run = self._worker_runs.get(run_id)
            return deepcopy(run) if run else None

    def get_worker_run_by_idempotency_key(self, key: str) -> WorkerRun | None:
        with self._lock:
            run_id = self._worker_run_idempotency.get(key)
            return self.get_worker_run(run_id) if run_id else None

    def list_worker_runs(self, task_id: str | None = None) -> list[WorkerRun]:
        with self._lock:
            runs = list(self._worker_runs.values())
            if task_id is not None:
                runs = [run for run in runs if run.task_id == task_id]
            return [deepcopy(run) for run in runs]

    def update_worker_run(self, worker_run: WorkerRun, expected_version: int) -> None:
        with self._lock:
            current = self._worker_runs.get(worker_run.run_id)
            if current is None or current.version != expected_version:
                raise ConflictError("WorkerRun optimistic lock conflict")
            updated = deepcopy(worker_run)
            updated.version = expected_version + 1
            self._worker_runs[worker_run.run_id] = updated

    def add_approval(self, approval: Approval) -> Approval:
        with self._lock:
            if approval.idempotency_key:
                existing_id = self._approval_idempotency.get(approval.idempotency_key)
                if existing_id:
                    return deepcopy(self._approvals[existing_id])
                self._approval_idempotency[approval.idempotency_key] = approval.approval_id
            if approval.approval_id in self._approvals:
                raise ConflictError(f"Approval {approval.approval_id} already exists")
            self._approvals[approval.approval_id] = deepcopy(approval)
            return deepcopy(approval)

    def get_approval(self, approval_id: str) -> Approval | None:
        with self._lock:
            approval = self._approvals.get(approval_id)
            return deepcopy(approval) if approval else None

    def get_approval_by_idempotency_key(self, key: str) -> Approval | None:
        with self._lock:
            approval_id = self._approval_idempotency.get(key)
            return self.get_approval(approval_id) if approval_id else None

    def list_approvals(self, project_id: str) -> list[Approval]:
        with self._lock:
            return [
                deepcopy(approval)
                for approval in self._approvals.values()
                if approval.project_id == project_id
            ]

    def update_approval(self, approval: Approval, expected_version: int) -> None:
        with self._lock:
            current = self._approvals.get(approval.approval_id)
            if current is None or current.version != expected_version:
                raise ConflictError("Approval optimistic lock conflict")
            updated = deepcopy(approval)
            updated.version = expected_version + 1
            self._approvals[approval.approval_id] = updated

    def add_audit_event(self, event: AuditEvent) -> None:
        with self._lock:
            self._audit_events.append(deepcopy(event))

    def list_audit_events(self, project_id: str) -> list[AuditEvent]:
        with self._lock:
            return [
                deepcopy(event) for event in self._audit_events if event.project_id == project_id
            ]


class InMemoryUnitOfWork:
    def __init__(self, repo: InMemoryRepository | None = None) -> None:
        self.repo = repo or InMemoryRepository()

    def __enter__(self) -> InMemoryUnitOfWork:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if exc_type:
            self.rollback()
        else:
            self.commit()

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None
