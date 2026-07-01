from __future__ import annotations

import subprocess
import threading
import time
import uuid
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import IO

from ai_org.adapters.sandbox.policy import SandboxPolicyError, validate_sandbox_spec
from ai_org.ports.sandbox import (
    SandboxAuditEvent,
    SandboxCommandResult,
    SandboxCommandSpec,
    SandboxCommandStatus,
)
from ai_org.security import redact


class DockerSandboxRunner:
    def __init__(self, *, docker_command: str = "docker") -> None:
        self.docker_command = docker_command

    def is_available(self) -> bool:
        try:
            result = subprocess.run(
                [self.docker_command, "version", "--format", "{{.Server.Version}}"],
                check=False,
                text=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        return result.returncode == 0

    def run(self, spec: SandboxCommandSpec) -> SandboxCommandResult:
        if not self.is_available():
            return SandboxCommandResult(
                status=SandboxCommandStatus.BLOCKED,
                command=spec.command,
                image=spec.policy.image,
                error="DOCKER_UNAVAILABLE",
                audit_events=[
                    SandboxAuditEvent(
                        "sandbox.blocked",
                        {"reason": "DOCKER_UNAVAILABLE", "backend": "docker"},
                    )
                ],
            )
        try:
            validate_sandbox_spec(spec)
        except SandboxPolicyError as exc:
            return SandboxCommandResult(
                status=SandboxCommandStatus.BLOCKED,
                command=spec.command,
                image=spec.policy.image,
                error=str(exc),
                audit_events=[SandboxAuditEvent("sandbox.policy_blocked", {"reason": str(exc)})],
            )

        container_name = f"ai-org-sandbox-{uuid.uuid4().hex[:12]}"
        command = self._docker_command(spec, container_name)
        started = time.monotonic()
        try:
            completed = _run_bounded(
                command,
                stdin=spec.stdin,
                timeout_seconds=spec.policy.resources.timeout_seconds,
                stdout_limit_bytes=spec.policy.resources.stdout_limit_bytes,
                stderr_limit_bytes=spec.policy.resources.stderr_limit_bytes,
            )
        except _ProcessTimedOut as exc:
            self._cleanup_container(container_name)
            return SandboxCommandResult(
                status=SandboxCommandStatus.TIMED_OUT,
                command=spec.command,
                exit_code=None,
                stdout_summary=_summarize(exc.stdout, spec.worktree_path, 4096),
                stderr_summary=_summarize(exc.stderr, spec.worktree_path, 4096),
                duration_ms=_elapsed_ms(started),
                timed_out=True,
                network_enabled=spec.policy.network.enabled,
                image=spec.policy.image,
                error="SANDBOX_TIMEOUT",
                audit_events=[
                    SandboxAuditEvent(
                        "sandbox.command_timed_out",
                        {"backend": "docker", "purpose": spec.purpose},
                    )
                ],
            )
        if completed.output_exceeded:
            self._cleanup_container(container_name)
            return SandboxCommandResult(
                status=SandboxCommandStatus.FAILED,
                command=spec.command,
                exit_code=completed.returncode,
                stdout_summary=_summarize(
                    completed.stdout, spec.worktree_path, spec.policy.resources.stdout_limit_bytes
                ),
                stderr_summary=_summarize(
                    completed.stderr, spec.worktree_path, spec.policy.resources.stderr_limit_bytes
                ),
                duration_ms=_elapsed_ms(started),
                timed_out=False,
                network_enabled=spec.policy.network.enabled,
                image=spec.policy.image,
                error="SANDBOX_OUTPUT_LIMIT_EXCEEDED",
                audit_events=[
                    SandboxAuditEvent(
                        "sandbox.output_limit_exceeded",
                        {"backend": "docker", "purpose": spec.purpose},
                    )
                ],
            )

        status = (
            SandboxCommandStatus.SUCCEEDED
            if completed.returncode == 0
            else SandboxCommandStatus.FAILED
        )
        return SandboxCommandResult(
            status=status,
            command=spec.command,
            exit_code=completed.returncode,
            stdout_summary=_summarize(
                completed.stdout, spec.worktree_path, spec.policy.resources.stdout_limit_bytes
            ),
            stderr_summary=_summarize(
                completed.stderr, spec.worktree_path, spec.policy.resources.stderr_limit_bytes
            ),
            duration_ms=_elapsed_ms(started),
            timed_out=False,
            network_enabled=spec.policy.network.enabled,
            image=spec.policy.image,
            error=None if completed.returncode == 0 else "SANDBOX_COMMAND_FAILED",
            audit_events=[
                SandboxAuditEvent(
                    "sandbox.command_completed",
                    {
                        "backend": "docker",
                        "purpose": spec.purpose,
                        "exit_code": completed.returncode,
                        "network_enabled": spec.policy.network.enabled,
                    },
                )
            ],
        )

    def _docker_command(self, spec: SandboxCommandSpec, container_name: str) -> list[str]:
        policy = spec.policy
        worktree = spec.worktree_path.resolve()
        mount_fields = [
            "type=bind",
            f"src={worktree}",
            f"dst={policy.mounts.container_workdir}",
        ]
        if policy.mounts.worktree_read_only:
            mount_fields.append("readonly")
        command = [
            self.docker_command,
            "run",
            "--rm",
            "--name",
            container_name,
            "--network",
            "none",
            "--user",
            policy.user,
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--read-only",
            "--pids-limit",
            str(policy.resources.pids_limit),
            "--cpus",
            policy.resources.cpus,
            "--memory",
            policy.resources.memory,
            "--workdir",
            policy.mounts.container_workdir,
            "--mount",
            ",".join(mount_fields),
        ]
        for tmpfs in policy.mounts.tmpfs:
            command.extend(["--tmpfs", tmpfs])
        for key, value in sorted(spec.env.items()):
            command.extend(["--env", f"{key}={value}"])
        command.append(policy.image)
        command.extend(spec.command)
        return command

    def _cleanup_container(self, container_name: str) -> None:
        subprocess.run(
            [self.docker_command, "rm", "-f", container_name],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )


@dataclass(frozen=True, slots=True)
class _BoundedProcessResult:
    returncode: int | None
    stdout: str
    stderr: str
    output_exceeded: bool


class _ProcessTimedOut(Exception):
    def __init__(self, stdout: str, stderr: str) -> None:
        super().__init__("process timed out")
        self.stdout = stdout
        self.stderr = stderr


def _run_bounded(
    command: list[str],
    *,
    stdin: str | None,
    timeout_seconds: int,
    stdout_limit_bytes: int,
    stderr_limit_bytes: int,
) -> _BoundedProcessResult:
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    output_exceeded = threading.Event()
    stdout_capture = _StreamCapture(stdout_limit_bytes, process, output_exceeded)
    stderr_capture = _StreamCapture(stderr_limit_bytes, process, output_exceeded)
    stdout_thread = threading.Thread(
        target=stdout_capture.read_from,
        args=(process.stdout,),
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=stderr_capture.read_from,
        args=(process.stderr,),
        daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()
    if stdin is not None and process.stdin is not None:
        try:
            process.stdin.write(stdin.encode("utf-8"))
            process.stdin.close()
        except OSError:
            pass
    try:
        returncode = process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        process.kill()
        stdout_thread.join(timeout=2)
        stderr_thread.join(timeout=2)
        raise _ProcessTimedOut(stdout_capture.text(), stderr_capture.text()) from exc
    stdout_thread.join(timeout=2)
    stderr_thread.join(timeout=2)
    return _BoundedProcessResult(
        returncode=returncode,
        stdout=stdout_capture.text(),
        stderr=stderr_capture.text(),
        output_exceeded=output_exceeded.is_set(),
    )


class _StreamCapture:
    def __init__(
        self,
        limit_bytes: int,
        process: subprocess.Popen[bytes],
        output_exceeded: threading.Event,
    ) -> None:
        self.limit_bytes = limit_bytes
        self.process = process
        self.output_exceeded = output_exceeded
        self._chunks: list[bytes] = []
        self._total = 0
        self._exceeded = False

    def read_from(self, stream: IO[bytes] | None) -> None:
        if stream is None:
            return
        while True:
            chunk = stream.read(4096)
            if not chunk:
                return
            remaining = self.limit_bytes - self._total
            if remaining > 0:
                self._chunks.append(chunk[:remaining])
                self._total += len(chunk[:remaining])
            if len(chunk) > remaining:
                self._exceeded = True
                self.output_exceeded.set()
                with suppress(OSError):
                    self.process.kill()
                return

    def text(self) -> str:
        value = b"".join(self._chunks).decode("utf-8", errors="replace")
        if self._exceeded:
            return value + "\n[TRUNCATED]"
        return value


def _summarize(value: str, worktree_path: Path, limit: int) -> str:
    text = value.replace(str(worktree_path.resolve()), "<worktree>")
    text = text.replace(worktree_path.resolve().as_posix(), "<worktree>")
    redacted = redact(text.strip())
    safe = redacted if isinstance(redacted, str) else "[REDACTED]"
    if len(safe) > limit:
        return safe[:limit] + "\n[TRUNCATED]"
    return safe


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)
