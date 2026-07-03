from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from ai_org.adapters.codex.clients import CodexTimeoutExpired, _jsonl_observability
from ai_org.adapters.codex.diagnostics import (
    CODEX_DIAGNOSTICS_ENV_VAR,
    CodexCliDiagnosticsRunner,
    build_exec_invocation,
    diagnostics_enabled,
    write_diagnostic_report,
)
from ai_org.adapters.workers.mock import MockReviewWorker
from ai_org.domain.enums import AgentResultStatus, ReviewDecision, RiskLevel, TaskStatus, WorkerType
from ai_org.domain.models import Task
from ai_org.protocols.schemas import AgentResult


def test_codex_diagnostics_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(CODEX_DIAGNOSTICS_ENV_VAR, raising=False)

    assert diagnostics_enabled() is False


def test_diagnostic_exec_invocation_sanitizes_safe_command(tmp_path: Path) -> None:
    prompt = "Reply OK without sk-test-secret"

    stdin_invocation = build_exec_invocation(
        command="codex",
        worktree_path=tmp_path,
        prompt=prompt,
        prompt_mode="stdin",
        sandbox="read-only",
        approval_policy="on-request",
    )
    arg_invocation = build_exec_invocation(
        command="codex",
        worktree_path=tmp_path,
        prompt=prompt,
        prompt_mode="argument",
        sandbox="read-only",
        approval_policy="on-request",
    )

    assert stdin_invocation.command[-1] == "-"
    assert stdin_invocation.stdin == prompt
    assert arg_invocation.command[-1] == prompt
    assert arg_invocation.stdin is None
    assert "sk-test-secret" not in stdin_invocation.safe_command
    assert "sk-test-secret" not in arg_invocation.safe_command
    assert str(tmp_path) not in stdin_invocation.safe_command
    assert str(tmp_path) not in arg_invocation.safe_command
    assert "<worktree>" in stdin_invocation.safe_command
    assert "<prompt>" in arg_invocation.safe_command


def test_diagnostic_jsonl_summary_omits_raw_auth_details(tmp_path: Path) -> None:
    home_auth = str(Path.home() / ".codex" / "auth.json")
    runner = CodexCliDiagnosticsRunner(
        runner=FakeDiagnosticRunner(
            stdout=(
                '{"type":"session.created","session_id":"sess_secret"}\n'
                '{"type":"thread.started","thread_id":"thread_secret"}\n'
                f"{json.dumps({'type': 'debug', 'path': home_auth})}\n"
            )
        )
    )

    result = runner.run_exec(
        scenario="D2-read-only",
        worktree_path=tmp_path,
        prompt="Reply with exactly OK.",
        prompt_mode="stdin",
        sandbox="read-only",
        timeout_seconds=10,
    )

    assert "sess_secret" not in result.stdout_summary
    assert "thread_secret" not in result.stdout_summary
    assert home_auth not in result.stdout_summary
    assert "codex_jsonl_events=3" in result.stdout_summary


def test_timeout_classification_covers_no_output_total_and_transport_stall() -> None:
    no_output = _jsonl_observability("")
    total = _jsonl_observability('{"type":"progress"}\n')
    transport = _jsonl_observability(
        '{"type":"thread.started","thread_id":"thread_test"}\n'
        '{"type":"error","message":"transport stalled"}\n'
    )

    assert no_output["timeout_classification"] == "no_output_timeout"
    assert total["timeout_classification"] == "total_timeout"
    assert transport["timeout_classification"] == "transport_stall"


def test_diagnostic_timeout_records_process_tree_cleanup(tmp_path: Path) -> None:
    runner = CodexCliDiagnosticsRunner(
        runner=FakeDiagnosticRunner(timeout=True, stdout='{"type":"item.started"}\n')
    )

    result = runner.run_exec(
        scenario="D2-read-only",
        worktree_path=tmp_path,
        prompt="Reply with exactly OK.",
        prompt_mode="stdin",
        sandbox="read-only",
        timeout_seconds=10,
    )

    assert result.status == "timeout"
    assert result.timed_out is True
    assert result.timeout_classification == "stuck_after_item_started"
    assert result.process_killed is True
    assert result.process_tree_killed is True


def test_diagnostic_exec_runs_in_task_worktree_and_report_is_not_merge_candidate(
    tmp_path: Path,
) -> None:
    fake_runner = FakeDiagnosticRunner(stdout='{"type":"turn.completed"}\n')
    runner = CodexCliDiagnosticsRunner(runner=fake_runner)

    result = runner.run_exec(
        scenario="D2-read-only",
        worktree_path=tmp_path,
        prompt="Reply with exactly OK.",
        prompt_mode="stdin",
        sandbox="read-only",
        timeout_seconds=10,
    )
    report_path = tmp_path / "diagnostic.json"
    write_diagnostic_report(
        report_path,
        [result],
        status="Status: VERIFIED COMPLETE FOR CODEX CLI SINGLE-FILE DIAGNOSTIC",
        main_worktree_fingerprint_before="fingerprint",
        main_worktree_fingerprint_after="fingerprint",
        main_worktree_status_after="",
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    call_command = fake_runner.calls[0]["command"]
    assert isinstance(call_command, list)

    assert fake_runner.calls[0]["cwd"] == tmp_path
    assert "--cd" in call_command
    assert str(tmp_path) in call_command
    assert result.command.endswith("--cd <worktree> --color never -")
    assert report["merge_candidate_generated"] is False
    assert report["auto_merge"] is False
    assert report["auto_push"] is False
    assert report["main_worktree_fingerprint_match"] is True


def test_review_rejects_codex_diagnostic_timeout() -> None:
    task = Task(
        task_id="task_codex_diag",
        project_id="proj_codex_diag",
        title="Diagnostic timeout",
        objective="Verify timeout rejection",
        worker_type=WorkerType.CODEX.value,
        status=TaskStatus.READY,
        risk_level=RiskLevel.LOW,
        dependencies=[],
        acceptance_criteria=["diagnostic timeout rejected"],
        max_attempts=1,
        metadata={"codex_mode": "local_stepwise_multi_file_task"},
    )
    result = AgentResult(
        task_id=task.task_id,
        status=AgentResultStatus.FAILED,
        summary="Codex CLI diagnostic timed out.",
        artifacts=[],
        evidence=[],
        tests_run=[],
        assumptions=[],
        risks=[],
        unresolved_questions=[],
        metadata={
            "coding_worker": True,
            "blocked_reason": "CODEX_CLI_DIAGNOSTIC_TIMEOUT",
            "timeout_classification": "transport_stall",
            "policy_violations": [],
        },
    )

    report = MockReviewWorker().review(task, result, 1)

    assert report.decision == ReviewDecision.REJECTED
    assert "codex:timeout" in report.defects


class FakeDiagnosticRunner:
    def __init__(self, *, timeout: bool = False, stdout: str = "") -> None:
        self.timeout = timeout
        self.stdout = stdout
        self.calls: list[dict[str, object]] = []

    def __call__(
        self, command: list[str], cwd: Path, stdin: str | None, timeout_seconds: int
    ) -> subprocess.CompletedProcess[str]:
        self.calls.append(
            {
                "command": command,
                "cwd": cwd,
                "stdin": stdin,
                "timeout_seconds": timeout_seconds,
            }
        )
        if self.timeout:
            raise CodexTimeoutExpired(
                command,
                timeout_seconds,
                output=self.stdout,
                stderr="",
                elapsed_ms=timeout_seconds * 1000,
                process_killed=True,
                process_tree_killed=True,
                cleanup_error="",
            )
        result = subprocess.CompletedProcess(command, 0, stdout=self.stdout, stderr="")
        vars(result)["duration_ms"] = 123
        return result
