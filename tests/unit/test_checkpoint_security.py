from __future__ import annotations

import os
import threading

import pytest

from ai_org.orchestration.checkpoint_security import (
    ALLOWED_MSGPACK_MODULES,
    STRICT_MSGPACK_ENV,
    assert_checkpoint_security,
    assert_state_is_safe,
    build_serializer,
)


def test_strict_msgpack_is_configured_on_import() -> None:
    assert os.environ[STRICT_MSGPACK_ENV] == "true"
    assert_checkpoint_security()


def test_serializer_rejects_illegal_checkpoint_types() -> None:
    serializer = build_serializer()

    with pytest.raises(TypeError):
        serializer.dumps_typed({"callable": lambda: None})
    with pytest.raises(TypeError):
        serializer.dumps_typed({"lock": threading.Lock()})


def test_serializer_rejects_pickle_and_unknown_deserialization_payloads() -> None:
    serializer = build_serializer()

    with pytest.raises(NotImplementedError):
        serializer.loads_typed(("pickle", b"not-a-valid-or-allowed-pickle"))
    with pytest.raises(NotImplementedError):
        serializer.loads_typed(("unsupported", b"{}"))


def test_allowed_msgpack_modules_are_explicit() -> None:
    assert ALLOWED_MSGPACK_MODULES
    assert ("builtins",) in ALLOWED_MSGPACK_MODULES


def test_state_safety_rejects_executable_objects() -> None:
    with pytest.raises(TypeError):
        assert_state_is_safe({"bad": object()})
