from __future__ import annotations

from dataclasses import replace

import pytest

from ai_org.adapters.memory.repositories import InMemoryRepository
from ai_org.domain.enums import ProjectStatus
from ai_org.domain.errors import ConflictError
from ai_org.domain.models import Project


def test_project_optimistic_lock(repo: InMemoryRepository) -> None:
    project = Project(
        project_id="p1",
        title="t",
        goal="g",
        status=ProjectStatus.CREATED,
        success_criteria=[],
    )
    repo.add_project(project)
    stored = repo.get_project("p1")
    assert stored is not None

    repo.update_project(replace(stored, status=ProjectStatus.RUNNING), expected_version=0)
    with pytest.raises(ConflictError):
        repo.update_project(replace(stored, status=ProjectStatus.FAILED), expected_version=0)
