from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from ai_org.domain.enums import AgentResultStatus
from ai_org.domain.models import Task
from ai_org.protocols.schemas import WorkerTestRecord


@dataclass(frozen=True, slots=True)
class CommandLogEntry:
    command: str
    status: str
    exit_code: int | None = None
    cwd: str = ""
    stdout_summary: str = ""
    stderr_summary: str = ""
    duration_ms: int = 0
    timed_out: bool = False
    network_requested: bool = False
    allowed: bool = True
    approval_required: bool = False
    timeout_type: str | None = None
    elapsed_ms: int = 0
    jsonl_event_count: int = 0
    jsonl_error_events: int = 0
    jsonl_file_change_events: int = 0
    last_jsonl_event_type: str = ""
    last_jsonl_event_types: list[str] = field(default_factory=list)
    approval_requested: bool = False
    timeout_classification: str = ""
    process_killed: bool | None = None
    process_tree_killed: bool | None = None
    cleanup_error: str = ""


@dataclass(frozen=True, slots=True)
class CodexTaskRequest:
    task: Task
    attempt_number: int
    worktree_path: Path
    prompt: str


@dataclass(frozen=True, slots=True)
class CodexTaskResult:
    status: AgentResultStatus
    summary: str
    evidence: list[str] = field(default_factory=list)
    tests_run: list[WorkerTestRecord] = field(default_factory=list)
    command_logs: list[CommandLogEntry] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    unresolved_questions: list[str] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)


class CodexClient(Protocol):
    def start_task(self, request: CodexTaskRequest) -> CodexTaskResult:
        """Start a coding task in an isolated worktree.

        Implementations in this stage must be deterministic and must not call a real Codex
        service unless a later stage explicitly enables that capability.
        """

    def continue_task(self, request: CodexTaskRequest) -> CodexTaskResult:
        """Continue a previously started task when an implementation supports it."""

    def get_status(self, task_id: str) -> str:
        """Return a stable client-side status string for observability."""

    def collect_result(self, task_id: str) -> CodexTaskResult | None:
        """Return a previously collected result when the client keeps local state."""

    def cancel_task(self, task_id: str) -> None:
        """Cancel or mark a client-side task as abandoned."""
