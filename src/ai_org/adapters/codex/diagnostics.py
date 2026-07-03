from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

from ai_org.adapters.codex.clients import (
    _jsonl_metadata,
    _jsonl_observability,
    _looks_auth_required,
    _path_redactions,
    _run_subprocess,
    _summarize,
    _summarize_codex_jsonl,
    _timeout_bool,
    _timeout_cleanup_error,
    _timeout_elapsed_ms,
    _timeout_value,
    _version_summary,
)
from ai_org.security import redact

CODEX_DIAGNOSTICS_ENV_VAR = "AI_ORG_ENABLE_REAL_CODEX_DIAGNOSTICS"
PromptMode = Literal["stdin", "argument"]
CodexCommandRunner = Callable[[list[str], Path, str | None, int], subprocess.CompletedProcess[str]]


@dataclass(frozen=True, slots=True)
class CodexDiagnosticCommandResult:
    scenario: str
    command_shape: str
    command: str
    status: str
    exit_code: int | None
    duration_ms: int
    timeout_seconds: int
    timed_out: bool = False
    stdout_summary: str = ""
    stderr_summary: str = ""
    version: str = ""
    preflight_passed: bool | None = None
    auth_required: bool = False
    jsonl_event_count: int = 0
    jsonl_error_events: int = 0
    jsonl_file_change_events: int = 0
    last_jsonl_event_type: str = ""
    last_jsonl_event_types: list[str] = field(default_factory=list)
    approval_requested: bool = False
    timeout_classification: str = ""
    process_killed: bool | None = None
    process_tree_killed: bool | None = None
    cleanup_error: str = ""

    def to_report_dict(self) -> dict[str, object]:
        payload = asdict(self)
        redacted = redact(payload)
        return redacted if isinstance(redacted, dict) else {"redacted": True}


@dataclass(frozen=True, slots=True)
class CodexExecInvocation:
    command: list[str]
    stdin: str | None
    safe_command: str
    command_shape: str


class CodexCliDiagnosticsRunner:
    def __init__(
        self,
        *,
        command: str = "codex",
        runner: CodexCommandRunner = _run_subprocess,
    ) -> None:
        self.command = command
        self._runner = runner

    def run_version(self, cwd: Path, *, timeout_seconds: int = 15) -> CodexDiagnosticCommandResult:
        return self._run_command(
            scenario="D1-version",
            command=[self.command, "--version"],
            cwd=cwd,
            stdin=None,
            timeout_seconds=timeout_seconds,
            safe_command="codex --version",
            command_shape="version",
            summarize_jsonl=False,
        )

    def run_doctor(self, cwd: Path, *, timeout_seconds: int = 30) -> CodexDiagnosticCommandResult:
        result = self._run_command(
            scenario="D1-doctor",
            command=[self.command, "doctor", "--json"],
            cwd=cwd,
            stdin=None,
            timeout_seconds=timeout_seconds,
            safe_command="codex doctor --json",
            command_shape="doctor",
            summarize_jsonl=False,
        )
        return result

    def run_exec(
        self,
        *,
        scenario: str,
        worktree_path: Path,
        prompt: str,
        prompt_mode: PromptMode,
        sandbox: str,
        approval_policy: str = "on-request",
        timeout_seconds: int,
    ) -> CodexDiagnosticCommandResult:
        invocation = build_exec_invocation(
            command=self.command,
            worktree_path=worktree_path,
            prompt=prompt,
            prompt_mode=prompt_mode,
            sandbox=sandbox,
            approval_policy=approval_policy,
        )
        return self._run_command(
            scenario=scenario,
            command=invocation.command,
            cwd=worktree_path,
            stdin=invocation.stdin,
            timeout_seconds=timeout_seconds,
            safe_command=invocation.safe_command,
            command_shape=invocation.command_shape,
            summarize_jsonl=True,
        )

    def _run_command(
        self,
        *,
        scenario: str,
        command: list[str],
        cwd: Path,
        stdin: str | None,
        timeout_seconds: int,
        safe_command: str,
        command_shape: str,
        summarize_jsonl: bool,
    ) -> CodexDiagnosticCommandResult:
        try:
            completed = self._runner(command, cwd, stdin, timeout_seconds)
        except FileNotFoundError:
            return CodexDiagnosticCommandResult(
                scenario=scenario,
                command_shape=command_shape,
                command=safe_command,
                status="not_installed",
                exit_code=None,
                duration_ms=0,
                timeout_seconds=timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = _timeout_value(exc.stdout)
            stderr = _timeout_value(exc.stderr)
            jsonl = _jsonl_observability(stdout) if summarize_jsonl else {}
            return CodexDiagnosticCommandResult(
                scenario=scenario,
                command_shape=command_shape,
                command=safe_command,
                status="timeout",
                exit_code=None,
                duration_ms=_timeout_elapsed_ms(exc),
                timeout_seconds=timeout_seconds,
                timed_out=True,
                stdout_summary=_safe_stdout(stdout, cwd, summarize_jsonl=summarize_jsonl),
                stderr_summary=_summarize(stderr, path_redactions=_path_redactions(cwd)),
                jsonl_event_count=_metadata_int(jsonl, "jsonl_event_count"),
                jsonl_error_events=_metadata_int(jsonl, "jsonl_error_events"),
                jsonl_file_change_events=_metadata_int(jsonl, "jsonl_file_change_events"),
                last_jsonl_event_type=_metadata_str(jsonl, "last_jsonl_event_type"),
                last_jsonl_event_types=_metadata_string_list(jsonl, "last_jsonl_event_types"),
                approval_requested=_metadata_bool(jsonl, "approval_requested"),
                timeout_classification=_metadata_str(jsonl, "timeout_classification"),
                process_killed=_timeout_bool(exc, "process_killed"),
                process_tree_killed=_timeout_bool(exc, "process_tree_killed"),
                cleanup_error=_summarize(_timeout_cleanup_error(exc)),
            )
        stdout = completed.stdout
        stderr = completed.stderr
        jsonl = _jsonl_observability(stdout) if summarize_jsonl else {}
        doctor = _doctor_summary(stdout) if command_shape == "doctor" else {}
        version = _version_summary(stdout) if command_shape == "version" else ""
        auth_required = _looks_auth_required(stdout, stderr)
        status = "completed" if completed.returncode == 0 else "failed"
        if summarize_jsonl and completed.returncode != 0 and not _completion_observed(stdout):
            status = "process_exit_without_completion"
        return CodexDiagnosticCommandResult(
            scenario=scenario,
            command_shape=command_shape,
            command=safe_command,
            status=status,
            exit_code=completed.returncode,
            duration_ms=_duration_ms(completed),
            timeout_seconds=timeout_seconds,
            stdout_summary=_safe_stdout(stdout, cwd, summarize_jsonl=summarize_jsonl),
            stderr_summary=_summarize(stderr, path_redactions=_path_redactions(cwd)),
            version=version,
            preflight_passed=doctor.get("preflight_passed"),
            auth_required=auth_required,
            jsonl_event_count=_metadata_int(jsonl, "jsonl_event_count"),
            jsonl_error_events=_metadata_int(jsonl, "jsonl_error_events"),
            jsonl_file_change_events=_metadata_int(jsonl, "jsonl_file_change_events"),
            last_jsonl_event_type=_metadata_str(jsonl, "last_jsonl_event_type"),
            last_jsonl_event_types=_metadata_string_list(jsonl, "last_jsonl_event_types"),
            approval_requested=_metadata_bool(jsonl, "approval_requested"),
            timeout_classification=_metadata_str(jsonl, "timeout_classification"),
        )


def diagnostics_enabled() -> bool:
    return os.environ.get(CODEX_DIAGNOSTICS_ENV_VAR, "").lower() == "true"


def build_exec_invocation(
    *,
    command: str,
    worktree_path: Path,
    prompt: str,
    prompt_mode: PromptMode,
    sandbox: str,
    approval_policy: str,
) -> CodexExecInvocation:
    base = [
        command,
        "--sandbox",
        sandbox,
        "--ask-for-approval",
        approval_policy,
        "exec",
        "--json",
        "--cd",
        str(worktree_path),
        "--color",
        "never",
    ]
    safe_base = (
        f"codex --sandbox {sandbox} --ask-for-approval {approval_policy} "
        "exec --json --cd <worktree> --color never"
    )
    if prompt_mode == "stdin":
        return CodexExecInvocation(
            command=[*base, "-"],
            stdin=prompt,
            safe_command=f"{safe_base} -",
            command_shape="stdin",
        )
    return CodexExecInvocation(
        command=[*base, prompt],
        stdin=None,
        safe_command=f"{safe_base} <prompt>",
        command_shape="argument",
    )


def write_diagnostic_report(
    path: Path,
    results: list[CodexDiagnosticCommandResult],
    *,
    status: str = "",
    main_worktree_fingerprint_before: str = "",
    main_worktree_fingerprint_after: str = "",
    main_worktree_status_after: str = "",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {
        "status": status,
        "main_worktree_fingerprint_before": main_worktree_fingerprint_before,
        "main_worktree_fingerprint_after": main_worktree_fingerprint_after,
        "main_worktree_status_after": main_worktree_status_after,
        "main_worktree_fingerprint_match": (
            bool(main_worktree_fingerprint_before)
            and main_worktree_fingerprint_before == main_worktree_fingerprint_after
        ),
        "merge_candidate_generated": False,
        "auto_merge": False,
        "auto_push": False,
        "results": [result.to_report_dict() for result in results],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _safe_stdout(stdout: str, cwd: Path, *, summarize_jsonl: bool) -> str:
    if summarize_jsonl:
        return _summarize_codex_jsonl(stdout)
    return _summarize(stdout, path_redactions=_path_redactions(cwd))


def _doctor_summary(stdout: str) -> dict[str, bool]:
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return {"preflight_passed": False}
    if not isinstance(payload, dict):
        return {"preflight_passed": False}
    checks = payload.get("checks")
    if not isinstance(checks, dict):
        return {"preflight_passed": False}
    auth = checks.get("auth.credentials")
    return {"preflight_passed": isinstance(auth, dict) and auth.get("status") == "ok"}


def _completion_observed(stdout: str) -> bool:
    metadata = _jsonl_metadata(stdout)
    if metadata.get("codex_thread_observed") or metadata.get("codex_session_observed"):
        return any(
            event_type in {"turn.completed", "response.completed", "item.completed"}
            for event_type in _metadata_string_list(
                _jsonl_observability(stdout), "last_jsonl_event_types"
            )
        )
    return False


def _duration_ms(result: subprocess.CompletedProcess[str]) -> int:
    value = vars(result).get("duration_ms", 0)
    return value if isinstance(value, int) else 0


def _metadata_int(metadata: dict[str, object], key: str) -> int:
    value = metadata.get(key)
    return value if isinstance(value, int) else 0


def _metadata_str(metadata: dict[str, object], key: str) -> str:
    value = metadata.get(key)
    return value if isinstance(value, str) else ""


def _metadata_bool(metadata: dict[str, object], key: str) -> bool:
    value = metadata.get(key)
    return value if isinstance(value, bool) else False


def _metadata_string_list(metadata: dict[str, object], key: str) -> list[str]:
    value = metadata.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]
