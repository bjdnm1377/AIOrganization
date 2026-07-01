from __future__ import annotations

from collections.abc import Mapping
from typing import Any

SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "secret",
    "token",
    "password",
    "env",
    "environment",
    "raw_prompt",
    "chain_of_thought",
}


def redact(value: Any) -> Any:
    if isinstance(value, Mapping):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if str(key).lower() in SENSITIVE_KEYS:
                redacted[str(key)] = "[REDACTED]"
            else:
                redacted[str(key)] = redact(item)
        return redacted
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return [redact(item) for item in value]
    if isinstance(value, str) and ("sk-" in value or "SECRET" in value or "TOKEN" in value):
        return "[REDACTED]"
    return value
