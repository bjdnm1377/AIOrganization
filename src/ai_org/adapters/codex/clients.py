from __future__ import annotations

import os
from pathlib import Path

from ai_org.domain.enums import AgentResultStatus
from ai_org.ports.codex import CodexClient, CodexTaskRequest, CodexTaskResult, CommandLogEntry
from ai_org.protocols.schemas import WorkerTestRecord


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
    def __init__(self, enable_env_var: str = "AI_ORG_ENABLE_REAL_CODEX") -> None:
        self.enable_env_var = enable_env_var
        self._results: dict[str, CodexTaskResult] = {}

    def start_task(self, request: CodexTaskRequest) -> CodexTaskResult:
        if os.environ.get(self.enable_env_var, "").lower() != "true":
            result = _not_configured_result(
                "Local Codex CLI execution is not configured or approved for this stage."
            )
            self._results[request.task.task_id] = result
            return result
        result = _not_configured_result(
            "Real Codex CLI execution is intentionally not implemented in this skeleton."
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


def _not_configured_result(summary: str) -> CodexTaskResult:
    return CodexTaskResult(
        status=AgentResultStatus.NOT_CONFIGURED,
        summary=summary,
        evidence=["No real Codex process was started."],
        tests_run=[WorkerTestRecord(name="codex-not-configured", status="skipped")],
        command_logs=[
            CommandLogEntry(
                command="codex.start",
                status="not_configured",
                approval_required=True,
                stdout_summary=summary,
            )
        ],
        assumptions=["A later approved stage must provide the real Codex adapter."],
        risks=["Coding task was not executed."],
        unresolved_questions=[],
        metadata={"codex_mode": "not_configured"},
    )


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
