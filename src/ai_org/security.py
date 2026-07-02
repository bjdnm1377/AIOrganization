from __future__ import annotations

import re
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

SECRET_MARKER_RE = re.compile(r"SECRET|TOKEN|PASSWORD")
OPENAI_KEY_RE = re.compile(r"\bsk-[A-Za-z0-9_-]{8,}")
GITHUB_TOKEN_RE = re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b")
BEARER_TOKEN_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}")
PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
    re.DOTALL,
)
WINDOWS_ABSOLUTE_PATH_RE = re.compile(r"(?i)\b[A-Z]:(?:\\\\|\\)[^\"'\s,}\]]+")
POSIX_ABSOLUTE_PATH_RE = re.compile(r"(?<![\w])/(?:Users|home|tmp|var|private|mnt)/[^\s\"',}\]]+")


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
    if isinstance(value, str):
        return _redact_text(value)
    return value


def sensitive_pattern_count(value: str) -> int:
    patterns = (
        SECRET_MARKER_RE,
        OPENAI_KEY_RE,
        GITHUB_TOKEN_RE,
        BEARER_TOKEN_RE,
        PRIVATE_KEY_RE,
    )
    return sum(len(pattern.findall(value)) for pattern in patterns)


def _looks_like_openai_key(value: str) -> bool:
    return OPENAI_KEY_RE.search(value) is not None


def _redact_text(value: str) -> str:
    if SECRET_MARKER_RE.search(value):
        return "[REDACTED]"
    redacted = OPENAI_KEY_RE.sub("[REDACTED]", value)
    redacted = GITHUB_TOKEN_RE.sub("[REDACTED]", redacted)
    redacted = BEARER_TOKEN_RE.sub("Bearer [REDACTED]", redacted)
    redacted = PRIVATE_KEY_RE.sub("[REDACTED PRIVATE KEY]", redacted)
    redacted = WINDOWS_ABSOLUTE_PATH_RE.sub("<path>", redacted)
    return POSIX_ABSOLUTE_PATH_RE.sub("<path>", redacted)
