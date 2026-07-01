from __future__ import annotations

import pytest

from ai_org.adapters.workers.mock import DefaultWorkerRegistry
from ai_org.domain.enums import WorkerType


def test_worker_registry_returns_mock_workers() -> None:
    registry = DefaultWorkerRegistry.create()

    assert registry.get_worker(WorkerType.RESEARCH.value).worker_type == "research"
    assert registry.get_worker(WorkerType.CODING.value).worker_type == "coding"
    assert registry.get_review_worker().worker_type == "review"


def test_worker_registry_rejects_unknown_worker() -> None:
    registry = DefaultWorkerRegistry.create()

    with pytest.raises(KeyError):
        registry.get_worker("unknown")
