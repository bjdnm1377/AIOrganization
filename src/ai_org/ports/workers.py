from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ai_org.domain.models import Task
from ai_org.protocols.schemas import AgentResult, ReviewReport


@dataclass(frozen=True, slots=True)
class WorkerRequest:
    task: Task
    attempt_number: int
    structured_input: dict[str, object]


class Worker(Protocol):
    worker_type: str

    def run(self, request: WorkerRequest) -> AgentResult: ...


class ReviewWorker(Protocol):
    worker_type: str

    def review(self, task: Task, result: AgentResult, attempt_number: int) -> ReviewReport: ...


class WorkerRegistry(Protocol):
    def get_worker(self, worker_type: str) -> Worker: ...
    def get_review_worker(self) -> ReviewWorker: ...
