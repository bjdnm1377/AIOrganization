from __future__ import annotations

from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import PurePosixPath
from typing import Any

from ai_org.domain.models import Task

DEFAULT_FORBIDDEN_FILES = [
    ".env",
    ".env.*",
    ".github/**",
    "alembic/**",
    "pyproject.toml",
    "requirements-lock.txt",
]


@dataclass(frozen=True, slots=True)
class CodingWorkerPolicy:
    mode: str = "dry_run"
    allowed_files: list[str] = field(default_factory=lambda: ["**"])
    forbidden_files: list[str] = field(default_factory=lambda: list(DEFAULT_FORBIDDEN_FILES))
    allowed_commands: list[str] = field(default_factory=list)
    forbidden_commands: list[str] = field(default_factory=list)
    required_tests: list[str] = field(default_factory=list)
    mock_output_file: str = "codex_mock_output.txt"
    simulate_forbidden_file: bool = False
    simulate_test_failure: bool = False
    simulate_not_configured: bool = False
    simulate_secret_output: bool = False

    @classmethod
    def from_task(cls, task: Task) -> CodingWorkerPolicy:
        metadata = task.metadata
        forbidden_files = [
            *DEFAULT_FORBIDDEN_FILES,
            *_string_list(metadata.get("forbidden_files"), default=[]),
        ]
        return cls(
            mode=_string(metadata.get("codex_mode"), default="dry_run"),
            allowed_files=_string_list(metadata.get("allowed_files"), default=["**"]),
            forbidden_files=_deduplicate(forbidden_files),
            allowed_commands=_string_list(metadata.get("allowed_commands"), default=[]),
            forbidden_commands=_string_list(metadata.get("forbidden_commands"), default=[]),
            required_tests=_string_list(metadata.get("required_tests"), default=[]),
            mock_output_file=_string(
                metadata.get("mock_output_file"), default="codex_mock_output.txt"
            ),
            simulate_forbidden_file=bool(metadata.get("simulate_forbidden_file", False)),
            simulate_test_failure=bool(metadata.get("simulate_test_failure", False)),
            simulate_not_configured=bool(metadata.get("simulate_not_configured", False)),
            simulate_secret_output=bool(metadata.get("simulate_secret_output", False)),
        )

    def normalize_path(self, path: str) -> str:
        normalized = PurePosixPath(path.replace("\\", "/"))
        if normalized.is_absolute() or ".." in normalized.parts:
            raise ValueError(f"Unsafe path is not allowed: {path}")
        return normalized.as_posix()

    def is_file_allowed(self, path: str) -> bool:
        normalized = self.normalize_path(path)
        if any(_matches(normalized, pattern) for pattern in self.forbidden_files):
            return False
        return any(_matches(normalized, pattern) for pattern in self.allowed_files)

    def file_violations(self, paths: list[str]) -> list[str]:
        violations: list[str] = []
        for path in paths:
            try:
                if not self.is_file_allowed(path):
                    violations.append(path)
            except ValueError:
                violations.append(path)
        return sorted(set(violations))

    def command_violations(self, commands: list[str]) -> list[str]:
        violations: list[str] = []
        for command in commands:
            if self._is_command_forbidden(command) or not self._is_command_allowed(command):
                violations.append(command)
        return violations

    def _is_command_allowed(self, command: str) -> bool:
        if not self.allowed_commands:
            return False
        return any(
            command == allowed or command.startswith(f"{allowed} ")
            for allowed in self.allowed_commands
        )

    def _is_command_forbidden(self, command: str) -> bool:
        return any(
            command == forbidden or command.startswith(f"{forbidden} ")
            for forbidden in self.forbidden_commands
        )


def _matches(path: str, pattern: str) -> bool:
    normalized = pattern.replace("\\", "/")
    if normalized == "**":
        return True
    return fnmatch(path, normalized)


def _string(value: Any, *, default: str) -> str:
    return value if isinstance(value, str) and value else default


def _string_list(value: Any, *, default: list[str]) -> list[str]:
    if not isinstance(value, list):
        return default
    return [item for item in value if isinstance(item, str) and item]


def _deduplicate(values: list[str]) -> list[str]:
    deduplicated: list[str] = []
    for value in values:
        if value not in deduplicated:
            deduplicated.append(value)
    return deduplicated
