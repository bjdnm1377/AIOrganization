from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_org.domain.enums import AgentResultStatus
from ai_org.ports.codex import (
    CodexClient,
    CodexTaskRequest,
    CodexTaskResult,
    CommandLogEntry,
)
from ai_org.protocols.schemas import WorkerTestRecord
from ai_org.security import redact

ProcessRunner = Callable[[list[str], Path, str | None, int], subprocess.CompletedProcess[str]]

AUTH_REQUIRED_MARKERS = (
    "not logged in",
    "login required",
    "not authenticated",
    "authentication required",
    "auth required",
    "please log in",
    "codex login",
)

ALLOWED_SANDBOX_MODES = {"read-only", "workspace-write"}
ALLOWED_APPROVAL_POLICIES = {"on-request", "untrusted"}
SUMMARY_LIMIT = 800
WINDOWS_ABSOLUTE_PATH = re.compile(r"(?i)\b[A-Z]:(?:\\\\|\\)[^\"'\s,}\]]+")
POSIX_ABSOLUTE_PATH = re.compile(r"(?<![\w])/(?:Users|home|tmp|var|private|mnt)/[^\s\"',}\]]+")
CODE_TASK_ENV_VAR = "AI_ORG_ENABLE_REAL_CODEX_CODE_TASK"
MULTI_FILE_TASK_ENV_VAR = "AI_ORG_ENABLE_REAL_CODEX_MULTI_FILE_TASK"


class CodexTimeoutExpired(subprocess.TimeoutExpired):
    def __init__(
        self,
        cmd: str | bytes | os.PathLike[str] | os.PathLike[bytes] | Sequence[str | bytes],
        timeout: float,
        *,
        output: str = "",
        stderr: str = "",
        elapsed_ms: int = 0,
        process_killed: bool | None = None,
        process_tree_killed: bool | None = None,
        cleanup_error: str = "",
    ) -> None:
        super().__init__(cmd, timeout, output=output, stderr=stderr)
        self.elapsed_ms = elapsed_ms
        self.process_killed = process_killed
        self.process_tree_killed = process_tree_killed
        self.cleanup_error = cleanup_error


@dataclass(frozen=True, slots=True)
class _OptInConfig:
    mode: str
    env_var: str
    blocked_reason: str
    disabled_summary: str
    task_label: str


class DryRunCodexClient(CodexClient):
    def __init__(self) -> None:
        self._results: dict[str, CodexTaskResult] = {}

    def start_task(self, request: CodexTaskRequest) -> CodexTaskResult:
        result = CodexTaskResult(
            status=AgentResultStatus.DRY_RUN,
            summary="Codex client is in dry-run mode; no process was started.",
            evidence=["No real Codex command or API call was made."],
            tests_run=[WorkerTestRecord(name="codex-dry-run", status="skipped")],
            command_logs=[
                CommandLogEntry(
                    command="codex.start",
                    status="skipped",
                    approval_required=True,
                    stdout_summary="Real Codex execution is disabled for this stage.",
                )
            ],
            assumptions=["DryRunCodexClient is deterministic and local-only."],
            metadata={"codex_mode": "dry_run"},
        )
        self._results[request.task.task_id] = result
        return result

    def get_status(self, task_id: str) -> str:
        return "completed" if task_id in self._results else "not_started"

    def continue_task(self, request: CodexTaskRequest) -> CodexTaskResult:
        return self._results.get(request.task.task_id) or self.start_task(request)

    def collect_result(self, task_id: str) -> CodexTaskResult | None:
        return self._results.get(task_id)

    def cancel_task(self, task_id: str) -> None:
        self._results.pop(task_id, None)


class MockCodexClient(CodexClient):
    def __init__(self) -> None:
        self._results: dict[str, CodexTaskResult] = {}

    def start_task(self, request: CodexTaskRequest) -> CodexTaskResult:
        if request.task.metadata.get("simulate_not_configured"):
            result = _not_configured_result("Mock client was asked to simulate NOT_CONFIGURED.")
            self._results[request.task.task_id] = result
            return result
        output_file = _output_file(request)
        target = _safe_target(request.worktree_path, output_file)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_mock_file_body(request), encoding="utf-8")
        failed = bool(request.task.metadata.get("simulate_test_failure", False))
        tests = _test_records(request, failed=failed)
        logs = _command_logs(request, failed=failed)
        result = CodexTaskResult(
            status=AgentResultStatus.SUCCEEDED,
            summary="Mock Codex coding task completed in an isolated worktree.",
            evidence=[f"Modified {output_file} in worktree {request.worktree_path.name}."],
            tests_run=tests,
            command_logs=logs,
            assumptions=["MockCodexClient does not execute shell commands or call external APIs."],
            risks=[],
            unresolved_questions=[],
            metadata={
                "codex_mode": "mock",
                "mock_output_file": output_file,
                "simulated_test_failure": failed,
            },
        )
        self._results[request.task.task_id] = result
        return result

    def get_status(self, task_id: str) -> str:
        return "completed" if task_id in self._results else "not_started"

    def continue_task(self, request: CodexTaskRequest) -> CodexTaskResult:
        return self._results.get(request.task.task_id) or self.start_task(request)

    def collect_result(self, task_id: str) -> CodexTaskResult | None:
        return self._results.get(task_id)

    def cancel_task(self, task_id: str) -> None:
        self._results.pop(task_id, None)


class LocalCodexCliClient(CodexClient):
    def __init__(
        self,
        enable_env_var: str = "AI_ORG_ENABLE_REAL_CODEX_SMOKE",
        command: str = "codex",
        timeout_seconds: int = 180,
        runner: ProcessRunner | None = None,
    ) -> None:
        self.enable_env_var = enable_env_var
        self.command = command
        self.timeout_seconds = timeout_seconds
        self._runner = runner or _run_subprocess
        self._runner_overridden = runner is not None
        self._results: dict[str, CodexTaskResult] = {}

    def start_task(self, request: CodexTaskRequest) -> CodexTaskResult:
        opt_in = _opt_in_config(request, self.enable_env_var)
        if os.environ.get(opt_in.env_var, "").lower() != "true":
            result = _not_configured_result(
                opt_in.disabled_summary,
                metadata={
                    "codex_mode": opt_in.mode,
                    "opt_in_enabled": False,
                    "enable_env_var": opt_in.env_var,
                    "blocked_reason": opt_in.blocked_reason,
                },
            )
            self._results[request.task.task_id] = result
            return result
        if not self._runner_overridden and shutil.which(self.command) is None:
            result = _not_configured_result(
                "Codex CLI is not installed or is not on PATH.",
                metadata={
                    "codex_mode": opt_in.mode,
                    "opt_in_enabled": True,
                    "blocked_reason": "CODEX_CLI_NOT_INSTALLED",
                },
            )
            self._results[request.task.task_id] = result
            return result
        config_error = _configuration_error(request)
        if config_error is not None:
            result = _failed_result(
                config_error,
                logs=[],
                metadata={
                    "codex_mode": opt_in.mode,
                    "opt_in_enabled": True,
                    "blocked_reason": "CODEX_CLI_POLICY_BLOCKED",
                },
            )
            self._results[request.task.task_id] = result
            return result

        logs: list[CommandLogEntry] = []
        logical_cwd = _logical_cwd(request)
        path_redactions = _path_redactions(request.worktree_path)
        try:
            version = self._run(
                [self.command, "--version"],
                request.worktree_path,
                None,
                min(self.timeout_seconds, 15),
            )
        except FileNotFoundError:
            result = _not_configured_result(
                "Codex CLI is not installed or is not on PATH.",
                metadata={
                    "codex_mode": opt_in.mode,
                    "opt_in_enabled": True,
                    "blocked_reason": "CODEX_CLI_NOT_INSTALLED",
                },
            )
            self._results[request.task.task_id] = result
            return result
        except subprocess.TimeoutExpired as exc:
            log = _timeout_log(
                "codex --version",
                logical_cwd,
                exc,
                timeout_type="CODEX_CLI_VERSION_TIMEOUT",
            )
            result = _failed_result(
                "Codex CLI version check timed out.",
                logs=[log],
                metadata={
                    "codex_mode": opt_in.mode,
                    "opt_in_enabled": True,
                    "blocked_reason": "CODEX_CLI_VERSION_TIMEOUT",
                    **_timeout_metadata(exc, timeout_type="CODEX_CLI_VERSION_TIMEOUT"),
                },
            )
            self._results[request.task.task_id] = result
            return result
        version_log = _completed_log("codex --version", logical_cwd, version)
        logs.append(version_log)
        if version.returncode != 0:
            result = _not_configured_result(
                "Codex CLI version check failed.",
                command_logs=logs,
                metadata={
                    "codex_mode": opt_in.mode,
                    "opt_in_enabled": True,
                    "blocked_reason": "CODEX_CLI_VERSION_FAILED",
                },
            )
            self._results[request.task.task_id] = result
            return result

        doctor_metadata: dict[str, object] = {}
        try:
            doctor = self._run(
                [self.command, "doctor", "--json"],
                request.worktree_path,
                None,
                min(self.timeout_seconds, 30),
            )
        except subprocess.TimeoutExpired as exc:
            logs.append(
                _timeout_log(
                    "codex doctor --json",
                    logical_cwd,
                    exc,
                    network_requested=True,
                    path_redactions=path_redactions,
                    timeout_type="CODEX_CLI_PREFLIGHT_TIMEOUT",
                )
            )
            result = _not_configured_result(
                f"Codex CLI preflight timed out before {opt_in.task_label} execution.",
                command_logs=logs,
                metadata={
                    "codex_mode": opt_in.mode,
                    "opt_in_enabled": True,
                    "blocked_reason": "CODEX_CLI_PREFLIGHT_TIMEOUT",
                    "codex_preflight_passed": False,
                    **_timeout_metadata(exc, timeout_type="CODEX_CLI_PREFLIGHT_TIMEOUT"),
                },
            )
            self._results[request.task.task_id] = result
            return result
        else:
            doctor_metadata = _doctor_metadata(doctor.stdout)
            logs.append(
                _doctor_log(
                    logical_cwd,
                    doctor,
                    doctor_metadata,
                    path_redactions=path_redactions,
                )
            )
            if doctor.returncode != 0:
                blocked_reason = (
                    "CODEX_CLI_AUTH_REQUIRED"
                    if _looks_auth_required(doctor.stdout, doctor.stderr)
                    else "CODEX_CLI_PREFLIGHT_FAILED"
                )
                result = _not_configured_result(
                    f"Codex CLI preflight failed before {opt_in.task_label} execution.",
                    command_logs=logs,
                    metadata={
                        "codex_mode": opt_in.mode,
                        "opt_in_enabled": True,
                        "blocked_reason": blocked_reason,
                        "codex_preflight_passed": False,
                    },
                )
                self._results[request.task.task_id] = result
                return result
            if not doctor_metadata.get("preflight_passed"):
                result = _not_configured_result(
                    "Codex CLI preflight did not confirm readiness.",
                    command_logs=logs,
                    metadata={
                        "codex_mode": opt_in.mode,
                        "opt_in_enabled": True,
                        "blocked_reason": "CODEX_CLI_PREFLIGHT_NOT_READY",
                        "codex_preflight_passed": False,
                    },
                )
                self._results[request.task.task_id] = result
                return result

        sandbox = _metadata_string(request.task.metadata, "codex_sandbox", "workspace-write")
        approval_policy = _metadata_string(
            request.task.metadata, "codex_approval_policy", "on-request"
        )
        exec_command = [
            self.command,
            "--sandbox",
            sandbox,
            "--ask-for-approval",
            approval_policy,
            "exec",
            "--json",
            "--cd",
            str(request.worktree_path),
            "--color",
            "never",
            "-",
        ]
        safe_command = (
            f"codex --sandbox {sandbox} --ask-for-approval {approval_policy} "
            "exec --json --cd <worktree> --color never -"
        )
        try:
            execution = self._run(
                exec_command,
                request.worktree_path,
                request.prompt,
                self.timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            logs.append(
                _timeout_log(
                    safe_command,
                    logical_cwd,
                    exc,
                    network_requested=True,
                    path_redactions=path_redactions,
                    timeout_type="CODEX_CLI_TIMEOUT",
                    summarize_codex_jsonl=True,
                )
            )
            timeout_metadata = _timeout_metadata(
                exc,
                timeout_type="CODEX_CLI_TIMEOUT",
                summarize_codex_jsonl=True,
            )
            result = _failed_result(
                f"Codex CLI {opt_in.task_label} execution timed out.",
                logs=logs,
                metadata={
                    "codex_mode": opt_in.mode,
                    "opt_in_enabled": True,
                    "codex_version": _version_summary(version.stdout),
                    "blocked_reason": "CODEX_CLI_TIMEOUT",
                    "sandbox_mode": sandbox,
                    "approval_policy": approval_policy,
                    "codex_preflight_passed": True,
                    "external_service_requested": True,
                    "external_service_used": True,
                    "codex_exec_timeout_seconds": self.timeout_seconds,
                    **timeout_metadata,
                },
            )
            self._results[request.task.task_id] = result
            return result

        logs.append(
            _completed_log(
                safe_command,
                logical_cwd,
                execution,
                network_requested=True,
                path_redactions=path_redactions,
                summarize_codex_jsonl=True,
            )
        )
        execution_metadata = _jsonl_metadata(execution.stdout)
        if execution.returncode != 0:
            auth_required = _looks_auth_required(execution.stdout, execution.stderr)
            result = (
                _not_configured_result(
                    f"Codex CLI authentication is required before {opt_in.task_label} execution.",
                    command_logs=logs,
                    metadata={
                        "codex_mode": opt_in.mode,
                        "opt_in_enabled": True,
                        "codex_version": _version_summary(version.stdout),
                        "blocked_reason": "CODEX_CLI_AUTH_REQUIRED",
                        "sandbox_mode": sandbox,
                        "approval_policy": approval_policy,
                        "codex_preflight_passed": True,
                        "external_service_requested": True,
                        **execution_metadata,
                    },
                )
                if auth_required
                else _failed_result(
                    f"Codex CLI {opt_in.task_label} execution failed.",
                    logs=logs,
                    metadata={
                        "codex_mode": opt_in.mode,
                        "opt_in_enabled": True,
                        "codex_version": _version_summary(version.stdout),
                        "blocked_reason": "CODEX_CLI_EXECUTION_FAILED",
                        "sandbox_mode": sandbox,
                        "approval_policy": approval_policy,
                        "codex_preflight_passed": True,
                        "external_service_requested": True,
                        **execution_metadata,
                    },
                )
            )
            self._results[request.task.task_id] = result
            return result

        result = CodexTaskResult(
            status=AgentResultStatus.SUCCEEDED,
            summary=(
                f"Codex CLI {opt_in.task_label} execution completed inside the isolated worktree."
            ),
            evidence=["Codex CLI exited 0 with workspace-write sandbox and on-request approval."],
            tests_run=[
                WorkerTestRecord(name=f"codex-real-{opt_in.mode}", status="passed"),
            ],
            command_logs=logs,
            assumptions=[
                "Task scope is limited by task metadata and independent diff review.",
                "No automatic commit or merge was performed.",
            ],
            risks=[
                "This real Codex task validates only a minimal local CLI path, "
                "not a production sandbox."
            ],
            unresolved_questions=[],
            metadata={
                "codex_mode": opt_in.mode,
                "opt_in_enabled": True,
                "codex_version": _version_summary(version.stdout),
                "sandbox_mode": sandbox,
                "approval_policy": approval_policy,
                "real_codex_started": True,
                "no_real_codex_started": False,
                "codex_preflight_passed": True,
                "external_service_requested": True,
                "external_service_used": True,
                **execution_metadata,
            },
        )
        self._results[request.task.task_id] = result
        return result

    def get_status(self, task_id: str) -> str:
        return "completed" if task_id in self._results else "not_started"

    def continue_task(self, request: CodexTaskRequest) -> CodexTaskResult:
        return self._results.get(request.task.task_id) or self.start_task(request)

    def collect_result(self, task_id: str) -> CodexTaskResult | None:
        return self._results.get(task_id)

    def cancel_task(self, task_id: str) -> None:
        self._results.pop(task_id, None)

    def _run(
        self, command: list[str], cwd: Path, stdin: str | None, timeout_seconds: int
    ) -> subprocess.CompletedProcess[str]:
        return self._runner(command, cwd, stdin, timeout_seconds)


def _not_configured_result(
    summary: str,
    *,
    command_logs: list[CommandLogEntry] | None = None,
    metadata: dict[str, object] | None = None,
) -> CodexTaskResult:
    result_metadata = {
        "no_real_codex_started": True,
        **(metadata or {"codex_mode": "not_configured"}),
    }
    return CodexTaskResult(
        status=AgentResultStatus.NOT_CONFIGURED,
        summary=summary,
        evidence=["No real Codex process was started."],
        tests_run=[WorkerTestRecord(name="codex-not-configured", status="skipped")],
        command_logs=command_logs
        or [
            CommandLogEntry(
                command="codex.start",
                status="not_configured",
                approval_required=True,
                stdout_summary=summary,
            )
        ],
        assumptions=["Real Codex smoke execution requires explicit local readiness."],
        risks=["Coding task was not executed."],
        unresolved_questions=[],
        metadata=result_metadata,
    )


def _opt_in_config(request: CodexTaskRequest, smoke_env_var: str) -> _OptInConfig:
    mode = _metadata_string(request.task.metadata, "codex_mode", "local_cli")
    if mode == "local_multi_file_task":
        return _OptInConfig(
            mode=mode,
            env_var=MULTI_FILE_TASK_ENV_VAR,
            blocked_reason="REAL_CODEX_MULTI_FILE_TASK_OPT_IN_REQUIRED",
            disabled_summary=(
                "Local Codex CLI multi-file task execution is disabled; "
                "explicit opt-in is required."
            ),
            task_label="multi-file task",
        )
    if mode == "local_code_task":
        return _OptInConfig(
            mode=mode,
            env_var=CODE_TASK_ENV_VAR,
            blocked_reason="REAL_CODEX_CODE_TASK_OPT_IN_REQUIRED",
            disabled_summary=(
                "Local Codex CLI code-task execution is disabled; explicit opt-in is required."
            ),
            task_label="code task",
        )
    return _OptInConfig(
        mode="local_cli",
        env_var=smoke_env_var,
        blocked_reason="REAL_CODEX_SMOKE_OPT_IN_REQUIRED",
        disabled_summary=(
            "Local Codex CLI smoke execution is disabled; explicit opt-in is required."
        ),
        task_label="smoke",
    )


def _failed_result(
    summary: str, *, logs: list[CommandLogEntry], metadata: dict[str, object]
) -> CodexTaskResult:
    return CodexTaskResult(
        status=AgentResultStatus.FAILED,
        summary=summary,
        evidence=["Real Codex CLI execution did not complete successfully."],
        tests_run=[WorkerTestRecord(name="codex-real-cli", status="failed")],
        command_logs=logs,
        assumptions=["The first-layer workflow must treat failed CLI execution as non-accepted."],
        risks=["Coding task was not accepted."],
        unresolved_questions=[],
        metadata=metadata,
    )


def _run_subprocess(
    command: list[str], cwd: Path, stdin: str | None, timeout_seconds: int
) -> subprocess.CompletedProcess[str]:
    started = time.monotonic()
    popen_kwargs: dict[str, Any] = {}
    if os.name == "nt":
        popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        popen_kwargs["start_new_session"] = True
    process = subprocess.Popen(
        command,
        cwd=str(cwd),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=_safe_environment(),
        **popen_kwargs,
    )
    try:
        stdout, stderr = process.communicate(input=stdin, timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        cleanup = _kill_process_tree(process)
        try:
            stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
            cleanup["process_killed"] = True
            cleanup["cleanup_error"] = _join_cleanup_errors(
                str(cleanup.get("cleanup_error", "")),
                "process did not exit after process-tree kill; killed parent process",
            )
        timeout = CodexTimeoutExpired(
            command,
            timeout_seconds,
            output=stdout or _timeout_value(exc.stdout),
            stderr=stderr or _timeout_value(exc.stderr),
            elapsed_ms=_elapsed_ms(started),
            process_killed=bool(cleanup.get("process_killed", False)),
            process_tree_killed=bool(cleanup.get("process_tree_killed", False)),
            cleanup_error=str(cleanup.get("cleanup_error", "")),
        )
        raise timeout from exc
    result = subprocess.CompletedProcess(
        command,
        process.returncode,
        stdout=stdout,
        stderr=stderr,
    )
    vars(result)["duration_ms"] = _elapsed_ms(started)
    return result


def _kill_process_tree(process: subprocess.Popen[str]) -> dict[str, object]:
    if process.poll() is not None:
        return {"process_killed": False, "process_tree_killed": False, "cleanup_error": ""}
    if os.name == "nt":
        try:
            result = subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                check=False,
                text=True,
                capture_output=True,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            process.kill()
            return {
                "process_killed": True,
                "process_tree_killed": False,
                "cleanup_error": str(exc),
            }
        if result.returncode == 0:
            return {"process_killed": True, "process_tree_killed": True, "cleanup_error": ""}
        process.kill()
        return {
            "process_killed": True,
            "process_tree_killed": False,
            "cleanup_error": _summarize(result.stderr or result.stdout),
        }
    killpg = getattr(os, "killpg", None)
    if not callable(killpg):
        process.kill()
        return {
            "process_killed": True,
            "process_tree_killed": False,
            "cleanup_error": "process-group kill is unavailable on this platform",
        }
    try:
        kill_signal = getattr(signal, "SIGKILL", signal.SIGTERM)
        killpg(process.pid, kill_signal)
        return {"process_killed": True, "process_tree_killed": True, "cleanup_error": ""}
    except ProcessLookupError:
        return {"process_killed": False, "process_tree_killed": False, "cleanup_error": ""}
    except OSError as exc:
        process.kill()
        return {
            "process_killed": True,
            "process_tree_killed": False,
            "cleanup_error": str(exc),
        }


def _safe_environment() -> dict[str, str]:
    keep = {
        "ALLUSERSPROFILE",
        "APPDATA",
        "CODEX_HOME",
        "COMSPEC",
        "HOME",
        "LANG",
        "LC_ALL",
        "LOCALAPPDATA",
        "PATH",
        "PATHEXT",
        "PROGRAMDATA",
        "PROGRAMFILES",
        "PROGRAMFILES(X86)",
        "SYSTEMDRIVE",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "USERDOMAIN",
        "USERNAME",
        "USERPROFILE",
        "WINDIR",
    }
    env: dict[str, str] = {}
    for key, value in os.environ.items():
        if key.upper() in keep:
            env[key] = value
    env["AI_ORG_CODEX_WORKER"] = "true"
    return env


def _configuration_error(request: CodexTaskRequest) -> str | None:
    sandbox = _metadata_string(request.task.metadata, "codex_sandbox", "workspace-write")
    approval_policy = _metadata_string(request.task.metadata, "codex_approval_policy", "on-request")
    if sandbox not in ALLOWED_SANDBOX_MODES:
        return f"Codex sandbox mode {sandbox!r} is not allowed for real CLI execution."
    if approval_policy not in ALLOWED_APPROVAL_POLICIES:
        return f"Codex approval policy {approval_policy!r} is not allowed for real CLI execution."
    return None


def _metadata_string(metadata: Mapping[str, object], key: str, default: str) -> str:
    value = metadata.get(key)
    return value if isinstance(value, str) and value else default


def _metadata_int(metadata: Mapping[str, object], key: str) -> int:
    value = metadata.get(key)
    return value if isinstance(value, int) else 0


def _metadata_str(metadata: Mapping[str, object], key: str) -> str:
    value = metadata.get(key)
    return value if isinstance(value, str) else ""


def _metadata_bool(metadata: Mapping[str, object], key: str) -> bool:
    value = metadata.get(key)
    return value if isinstance(value, bool) else False


def _logical_cwd(request: CodexTaskRequest) -> str:
    return f"worktree://codex/{request.task.task_id}/attempt-{request.attempt_number}"


def _completed_log(
    command: str,
    logical_cwd: str,
    result: subprocess.CompletedProcess[str],
    *,
    network_requested: bool = False,
    path_redactions: Mapping[str, str] | None = None,
    summarize_codex_jsonl: bool = False,
) -> CommandLogEntry:
    stdout_summary = (
        _summarize_codex_jsonl(result.stdout)
        if summarize_codex_jsonl
        else _summarize(result.stdout, path_redactions=path_redactions)
    )
    jsonl_observability = _jsonl_observability(result.stdout) if summarize_codex_jsonl else {}
    return CommandLogEntry(
        command=command,
        status="completed" if result.returncode == 0 else "failed",
        exit_code=result.returncode,
        cwd=logical_cwd,
        stdout_summary=stdout_summary,
        stderr_summary=_summarize(result.stderr, path_redactions=path_redactions),
        duration_ms=_duration_ms(result),
        elapsed_ms=_duration_ms(result),
        timed_out=False,
        network_requested=network_requested,
        allowed=True,
        approval_required=False,
        jsonl_event_count=_metadata_int(jsonl_observability, "jsonl_event_count"),
        jsonl_error_events=_metadata_int(jsonl_observability, "jsonl_error_events"),
        jsonl_file_change_events=_metadata_int(jsonl_observability, "jsonl_file_change_events"),
        last_jsonl_event_type=_metadata_str(jsonl_observability, "last_jsonl_event_type"),
        approval_requested=_metadata_bool(jsonl_observability, "approval_requested"),
    )


def _doctor_log(
    logical_cwd: str,
    result: subprocess.CompletedProcess[str],
    metadata: dict[str, object],
    *,
    path_redactions: Mapping[str, str] | None = None,
) -> CommandLogEntry:
    summary = (
        "codex doctor preflight passed"
        if metadata.get("preflight_passed")
        else "codex doctor preflight did not confirm readiness"
    )
    return CommandLogEntry(
        command="codex doctor --json",
        status="completed" if result.returncode == 0 else "failed",
        exit_code=result.returncode,
        cwd=logical_cwd,
        stdout_summary=summary,
        stderr_summary=_summarize(result.stderr, path_redactions=path_redactions),
        duration_ms=0,
        timed_out=False,
        network_requested=True,
        allowed=True,
        approval_required=False,
    )


def _timeout_log(
    command: str,
    logical_cwd: str,
    exc: subprocess.TimeoutExpired,
    *,
    network_requested: bool = False,
    path_redactions: Mapping[str, str] | None = None,
    timeout_type: str,
    summarize_codex_jsonl: bool = False,
) -> CommandLogEntry:
    stdout = _timeout_value(exc.stdout)
    stderr = _timeout_value(exc.stderr)
    jsonl_observability = _jsonl_observability(stdout) if summarize_codex_jsonl else {}
    stdout_summary = (
        _summarize_codex_jsonl(stdout)
        if summarize_codex_jsonl
        else _summarize(stdout, path_redactions=path_redactions)
    )
    return CommandLogEntry(
        command=command,
        status="timeout",
        exit_code=None,
        cwd=logical_cwd,
        stdout_summary=stdout_summary,
        stderr_summary=_summarize(stderr, path_redactions=path_redactions),
        duration_ms=_timeout_elapsed_ms(exc),
        elapsed_ms=_timeout_elapsed_ms(exc),
        timed_out=True,
        network_requested=network_requested,
        allowed=True,
        approval_required=False,
        timeout_type=timeout_type,
        jsonl_event_count=_metadata_int(jsonl_observability, "jsonl_event_count"),
        jsonl_error_events=_metadata_int(jsonl_observability, "jsonl_error_events"),
        jsonl_file_change_events=_metadata_int(jsonl_observability, "jsonl_file_change_events"),
        last_jsonl_event_type=_metadata_str(jsonl_observability, "last_jsonl_event_type"),
        approval_requested=_metadata_bool(jsonl_observability, "approval_requested"),
        process_killed=_timeout_bool(exc, "process_killed"),
        process_tree_killed=_timeout_bool(exc, "process_tree_killed"),
        cleanup_error=_summarize(_timeout_cleanup_error(exc)),
    )


def _timeout_value(value: str | bytes | None) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value or ""


def _elapsed_ms(started: float) -> int:
    return max(0, int((time.monotonic() - started) * 1000))


def _duration_ms(result: subprocess.CompletedProcess[str]) -> int:
    value = vars(result).get("duration_ms", 0)
    return value if isinstance(value, int) else 0


def _timeout_elapsed_ms(exc: subprocess.TimeoutExpired) -> int:
    return exc.elapsed_ms if isinstance(exc, CodexTimeoutExpired) else 0


def _timeout_bool(exc: subprocess.TimeoutExpired, name: str) -> bool | None:
    if not isinstance(exc, CodexTimeoutExpired):
        return None
    value = exc.process_killed if name == "process_killed" else exc.process_tree_killed
    return value if isinstance(value, bool) else None


def _timeout_cleanup_error(exc: subprocess.TimeoutExpired) -> str:
    return exc.cleanup_error if isinstance(exc, CodexTimeoutExpired) else ""


def _timeout_metadata(
    exc: subprocess.TimeoutExpired,
    *,
    timeout_type: str,
    summarize_codex_jsonl: bool = False,
) -> dict[str, object]:
    stdout = _timeout_value(exc.stdout)
    observability = _jsonl_observability(stdout) if summarize_codex_jsonl else {}
    return {
        "timeout_type": timeout_type,
        "timeout_seconds": exc.timeout,
        "timeout_elapsed_ms": _timeout_elapsed_ms(exc),
        "timeout_process_killed": _timeout_bool(exc, "process_killed"),
        "timeout_process_tree_killed": _timeout_bool(exc, "process_tree_killed"),
        "timeout_cleanup_error": _summarize(_timeout_cleanup_error(exc)),
        **observability,
        **(_jsonl_metadata(stdout) if summarize_codex_jsonl else {}),
    }


def _join_cleanup_errors(first: str, second: str) -> str:
    if first and second:
        return f"{first}; {second}"
    return first or second


def _summarize(value: str, *, path_redactions: Mapping[str, str] | None = None) -> str:
    raw = value.strip()
    for needle, replacement in (path_redactions or {}).items():
        raw = raw.replace(needle, replacement)
    raw = _redact_absolute_paths(raw)
    redacted = redact(raw)
    text = redacted if isinstance(redacted, str) else "[REDACTED]"
    text = text.replace("\r\n", "\n")
    if len(text) > SUMMARY_LIMIT:
        return text[:SUMMARY_LIMIT] + "\n[TRUNCATED]"
    return text


def _path_redactions(worktree_path: Path) -> dict[str, str]:
    resolved = worktree_path.resolve()
    redactions: dict[str, str] = {}
    for path, replacement in [
        (resolved, "<worktree>"),
        (resolved.parent, "<worktree-parent>"),
        (Path.home(), "<home>"),
    ]:
        _add_path_redaction(redactions, path, replacement)
    for name, replacement in [
        ("CODEX_HOME", "<codex-home>"),
        ("APPDATA", "<appdata>"),
        ("LOCALAPPDATA", "<localappdata>"),
        ("USERPROFILE", "<userprofile>"),
        ("TEMP", "<temp>"),
        ("TMP", "<temp>"),
    ]:
        value = os.environ.get(name)
        if value:
            _add_path_redaction(redactions, Path(value), replacement)
    return redactions


def _doctor_metadata(stdout: str) -> dict[str, object]:
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return {"preflight_passed": False}
    if not isinstance(payload, dict):
        return {"preflight_passed": False}
    checks = payload.get("checks")
    auth_ready = False
    if isinstance(checks, dict):
        auth = checks.get("auth.credentials")
        if isinstance(auth, dict):
            auth_ready = auth.get("status") == "ok"
    return {"preflight_passed": auth_ready}


def _version_summary(stdout: str) -> str:
    first_line = stdout.strip().splitlines()[0] if stdout.strip() else "unknown"
    return _summarize(first_line)


def _looks_auth_required(stdout: str, stderr: str) -> bool:
    haystack = f"{stdout}\n{stderr}".lower()
    return any(marker in haystack for marker in AUTH_REQUIRED_MARKERS)


def _jsonl_metadata(stdout: str) -> dict[str, object]:
    metadata: dict[str, object] = {
        "codex_thread_observed": False,
        "codex_session_observed": False,
    }
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        if _has_string(event, "session_id"):
            metadata["codex_session_observed"] = True
        if _has_string(event, "thread_id") or _has_string(event, "conversation_id"):
            metadata["codex_thread_observed"] = True
        nested = event.get("session")
        if isinstance(nested, dict):
            metadata["codex_session_observed"] = True
    return metadata


def _jsonl_observability(stdout: str) -> dict[str, object]:
    event_count = 0
    error_events = 0
    file_change_events = 0
    last_event_type = ""
    approval_requested = False
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        event_count += 1
        event_type = _event_type(event)
        last_event_type = event_type or last_event_type
        if event_type == "error":
            error_events += 1
        item = event.get("item")
        if isinstance(item, dict) and item.get("type") == "file_change":
            file_change_events += 1
        if _event_requests_approval(event):
            approval_requested = True
    return {
        "jsonl_event_count": event_count,
        "jsonl_error_events": error_events,
        "jsonl_file_change_events": file_change_events,
        "last_jsonl_event_type": last_event_type,
        "approval_requested": approval_requested,
    }


def _summarize_codex_jsonl(stdout: str) -> str:
    observability = _jsonl_observability(stdout)
    metadata = _jsonl_metadata(stdout)
    event_count = _metadata_int(observability, "jsonl_event_count")
    if event_count == 0:
        return _summarize(stdout)
    return (
        f"codex_jsonl_events={event_count}; "
        f"error_events={observability['jsonl_error_events']}; "
        f"file_change_events={observability['jsonl_file_change_events']}; "
        f"last_event={observability['last_jsonl_event_type']}; "
        f"approval_requested={str(observability['approval_requested']).lower()}; "
        f"thread_observed={str(metadata['codex_thread_observed']).lower()}; "
        f"session_observed={str(metadata['codex_session_observed']).lower()}"
    )


def _event_type(event: Mapping[str, Any]) -> str:
    value = event.get("type")
    if isinstance(value, str):
        return value
    item = event.get("item")
    if isinstance(item, dict):
        item_type = item.get("type")
        if isinstance(item_type, str):
            return f"item.{item_type}"
    return ""


def _event_requests_approval(event: Mapping[str, Any]) -> bool:
    text = json.dumps(event, sort_keys=True).lower()
    return "approval" in text or "permission" in text


def _has_string(event: Mapping[str, Any], key: str) -> bool:
    value = event.get(key)
    return isinstance(value, str) and bool(value)


def _add_path_redaction(redactions: dict[str, str], path: Path, replacement: str) -> None:
    try:
        resolved = path.resolve()
    except OSError:
        return
    if not str(resolved):
        return
    windows_path = str(resolved)
    posix_path = resolved.as_posix()
    for value in {windows_path, posix_path}:
        redactions[value] = replacement
        redactions[json.dumps(value)[1:-1]] = replacement


def _redact_absolute_paths(value: str) -> str:
    redacted = WINDOWS_ABSOLUTE_PATH.sub("<path>", value)
    return POSIX_ABSOLUTE_PATH.sub("<path>", redacted)


def _output_file(request: CodexTaskRequest) -> str:
    if request.task.metadata.get("simulate_forbidden_file"):
        return ".github/workflows/verification.yml"
    raw = request.task.metadata.get("mock_output_file")
    return raw if isinstance(raw, str) and raw else "codex_mock_output.txt"


def _safe_target(worktree_path: Path, relative_path: str) -> Path:
    target = (worktree_path / relative_path).resolve()
    try:
        target.relative_to(worktree_path.resolve())
    except ValueError as exc:
        raise ValueError(f"Mock output path escapes worktree: {relative_path}") from exc
    return target


def _mock_file_body(request: CodexTaskRequest) -> str:
    return "\n".join(
        [
            "Mock Codex artifact",
            f"task_id={request.task.task_id}",
            f"attempt={request.attempt_number}",
            f"objective={request.task.objective}",
            "",
        ]
    )


def _test_records(request: CodexTaskRequest, *, failed: bool) -> list[WorkerTestRecord]:
    tests = request.task.metadata.get("required_tests")
    names = [item for item in tests if isinstance(item, str)] if isinstance(tests, list) else []
    if not names:
        names = ["codex-mock-deterministic-check"]
    return [
        WorkerTestRecord(
            name=name,
            status="failed" if failed else "passed",
            details="Simulated failure." if failed else "Simulated pass.",
        )
        for name in names
    ]


def _command_logs(request: CodexTaskRequest, *, failed: bool) -> list[CommandLogEntry]:
    tests = request.task.metadata.get("required_tests")
    names = [item for item in tests if isinstance(item, str)] if isinstance(tests, list) else []
    if not names:
        return []
    stdout = (
        "SECRET value was redacted" if request.task.metadata.get("simulate_secret_output") else ""
    )
    return [
        CommandLogEntry(
            command=name,
            status="simulated",
            exit_code=1 if failed else 0,
            stdout_summary=stdout,
            stderr_summary="Simulated test failure." if failed else "",
            approval_required=False,
        )
        for name in names
    ]
