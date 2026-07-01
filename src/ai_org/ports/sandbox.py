from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Protocol


class SandboxCommandStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class SandboxResourceLimits:
    cpus: str = "1.0"
    memory: str = "512m"
    pids_limit: int = 128
    timeout_seconds: int = 120
    stdout_limit_bytes: int = 65536
    stderr_limit_bytes: int = 65536


@dataclass(frozen=True, slots=True)
class SandboxNetworkPolicy:
    enabled: bool = False
    approval_required: bool = True


@dataclass(frozen=True, slots=True)
class SandboxMount:
    host_path: Path
    container_path: str
    read_only: bool = True


@dataclass(frozen=True, slots=True)
class SandboxMountPolicy:
    container_workdir: str = "/workspace"
    worktree_read_only: bool = False
    tmpfs: tuple[str, ...] = ("/tmp:rw,noexec,nosuid,nodev,size=64m",)
    extra_mounts: tuple[SandboxMount, ...] = ()


@dataclass(frozen=True, slots=True)
class SandboxPolicy:
    image: str = "python:3.12-slim"
    user: str = "65532:65532"
    privileged: bool = False
    cap_drop: tuple[str, ...] = ("ALL",)
    security_options: tuple[str, ...] = ("no-new-privileges",)
    read_only_rootfs: bool = True
    network: SandboxNetworkPolicy = field(default_factory=SandboxNetworkPolicy)
    resources: SandboxResourceLimits = field(default_factory=SandboxResourceLimits)
    mounts: SandboxMountPolicy = field(default_factory=SandboxMountPolicy)


@dataclass(frozen=True, slots=True)
class SandboxCommandSpec:
    command: tuple[str, ...]
    worktree_path: Path
    policy: SandboxPolicy = field(default_factory=SandboxPolicy)
    stdin: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    purpose: str = "sandbox-command"


@dataclass(frozen=True, slots=True)
class SandboxAuditEvent:
    event_type: str
    payload: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SandboxCommandResult:
    status: SandboxCommandStatus
    command: tuple[str, ...]
    exit_code: int | None = None
    stdout_summary: str = ""
    stderr_summary: str = ""
    duration_ms: int = 0
    timed_out: bool = False
    network_enabled: bool = False
    image: str = ""
    error: str | None = None
    audit_events: list[SandboxAuditEvent] = field(default_factory=list)


class SandboxRunner(Protocol):
    def is_available(self) -> bool:
        """Return whether the concrete sandbox backend can run commands."""

    def run(self, spec: SandboxCommandSpec) -> SandboxCommandResult:
        """Run a command in a sandbox or return a structured BLOCKED result."""
