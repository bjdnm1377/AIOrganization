from __future__ import annotations

import shutil
import subprocess
from collections.abc import Iterator

import pytest

from ai_org.adapters.memory.repositories import InMemoryRepository
from ai_org.adapters.workers.mock import DefaultWorkerRegistry
from ai_org.application.service import ProjectApplicationService
from ai_org.orchestration.workflow import LangGraphWorkflow


@pytest.fixture
def repo() -> InMemoryRepository:
    return InMemoryRepository()


@pytest.fixture
def service(repo: InMemoryRepository) -> ProjectApplicationService:
    return ProjectApplicationService(repo, DefaultWorkerRegistry.create())


@pytest.fixture
def workflow(service: ProjectApplicationService) -> LangGraphWorkflow:
    return LangGraphWorkflow(service)


def docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        result = subprocess.run(
            ["docker", "info"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


@pytest.fixture
def require_docker() -> Iterator[None]:
    if not docker_available():
        pytest.skip("Docker is not available; PostgreSQL integration test skipped explicitly")
    yield
