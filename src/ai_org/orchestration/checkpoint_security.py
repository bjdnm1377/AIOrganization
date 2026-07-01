from __future__ import annotations

import os
from collections.abc import Iterable
from typing import Any

STRICT_MSGPACK_ENV = "LANGGRAPH_STRICT_MSGPACK"
ALLOWED_MSGPACK_MODULES: tuple[tuple[str, ...], ...] = (
    ("builtins",),
    ("datetime",),
    ("uuid",),
    ("ai_org", "protocols", "schemas"),
    ("ai_org", "domain", "enums"),
)


def configure_checkpoint_security() -> None:
    os.environ[STRICT_MSGPACK_ENV] = "true"


configure_checkpoint_security()

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer  # noqa: E402


def build_serializer(
    allowed_modules: Iterable[tuple[str, ...]] = ALLOWED_MSGPACK_MODULES,
) -> JsonPlusSerializer:
    return JsonPlusSerializer(
        pickle_fallback=False,
        allowed_msgpack_modules=tuple(allowed_modules),
    )


def assert_checkpoint_security() -> None:
    if os.environ.get(STRICT_MSGPACK_ENV) != "true":
        raise RuntimeError("LANGGRAPH_STRICT_MSGPACK=true must be configured before startup")
    serializer = build_serializer()
    serializer.dumps_typed({"self_check": True, "version": 1})
    for illegal in (_illegal_callable, object()):
        try:
            serializer.dumps_typed({"illegal": illegal})
        except TypeError:
            continue
        raise RuntimeError("Checkpoint serializer accepted an illegal type")


def assert_state_is_safe(value: Any) -> None:
    if isinstance(value, dict):
        for item in value.values():
            assert_state_is_safe(item)
        return
    if isinstance(value, list):
        for item in value:
            assert_state_is_safe(item)
        return
    if isinstance(value, tuple):
        for item in value:
            assert_state_is_safe(item)
        return
    if value is None or isinstance(value, str | int | float | bool):
        return
    if hasattr(value, "model_dump"):
        return
    raise TypeError(f"Unsafe checkpoint state type: {type(value)!r}")


def _illegal_callable() -> None:
    return None
