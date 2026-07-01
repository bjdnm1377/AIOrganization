from __future__ import annotations

import pytest

from ai_org.domain.enums import ProjectStatus, TaskStatus
from ai_org.domain.errors import InvalidTransitionError
from ai_org.domain.state_machine import ensure_project_transition, ensure_task_transition


def test_project_state_transitions() -> None:
    ensure_project_transition(ProjectStatus.CREATED, ProjectStatus.RUNNING)
    ensure_project_transition(ProjectStatus.RUNNING, ProjectStatus.COMPLETED)


def test_project_terminal_state_rejects_reopen() -> None:
    with pytest.raises(InvalidTransitionError):
        ensure_project_transition(ProjectStatus.COMPLETED, ProjectStatus.RUNNING)


def test_task_state_transitions_and_rework_limit_path() -> None:
    ensure_task_transition(TaskStatus.READY, TaskStatus.RUNNING)
    ensure_task_transition(TaskStatus.RUNNING, TaskStatus.REVIEWING)
    ensure_task_transition(TaskStatus.REVIEWING, TaskStatus.REWORK_REQUIRED)
    ensure_task_transition(TaskStatus.REWORK_REQUIRED, TaskStatus.RUNNING)


def test_task_accepted_cannot_run_again() -> None:
    with pytest.raises(InvalidTransitionError):
        ensure_task_transition(TaskStatus.ACCEPTED, TaskStatus.RUNNING)
