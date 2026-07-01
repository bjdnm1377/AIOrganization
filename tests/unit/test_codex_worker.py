from __future__ import annotations

import subprocess
from dataclasses import replace
from pathlib import Path

from ai_org.adapters.codex.clients import DryRunCodexClient, LocalCodexCliClient, MockCodexClient
from ai_org.adapters.codex.worker import CodexWorker
from ai_org.adapters.workers.mock import MockReviewWorker
from ai_org.domain.enums import AgentResultStatus, ReviewDecision, RiskLevel, TaskStatus, WorkerType
from ai_org.domain.models import Task
from ai_org.ports.codex import CodexTaskRequest, CodexTaskResult, CommandLogEntry
from ai_org.ports.workers import WorkerRequest
from ai_org.protocols.schemas import WorkerTestRecord


def test_mock_codex_worker_captures_diff_logs_and_artifacts(tmp_path: Path) -> None:
    repo = _git_repo(tmp_path / "repo")
    worker = CodexWorker(repo, client=MockCodexClient())
    task = _task(
        metadata={
            "codex_mode": "mock",
            "mock_output_file": "src/generated.txt",
            "allowed_files": ["src/generated.txt"],
            "allowed_commands": ["pytest"],
            "required_tests": ["pytest tests/unit/test_codex_worker.py"],
        }
    )

    result = worker.run(WorkerRequest(task=task, attempt_number=1, structured_input={}))

    assert result.status == AgentResultStatus.SUCCEEDED
    assert result.metadata["codex_mode"] == "mock"
    assert result.metadata["changed_files"] == ["src/generated.txt"]
    assert result.metadata["policy_violations"] == []
    assert {artifact.kind for artifact in result.artifacts} == {"markdown", "json", "patch"}
    assert _git(repo, "status", "--short").strip() == ""


def test_dry_run_codex_worker_does_not_start_real_codex(tmp_path: Path) -> None:
    repo = _git_repo(tmp_path / "repo")
    worker = CodexWorker(repo, client=DryRunCodexClient())
    task = _task(metadata={"codex_mode": "dry_run"})

    result = worker.run(WorkerRequest(task=task, attempt_number=1, structured_input={}))

    assert result.status == AgentResultStatus.DRY_RUN
    assert result.metadata["no_real_codex_started"] is True
    assert result.metadata["changed_files"] == []


def test_local_cli_client_returns_not_configured_without_permission(tmp_path: Path) -> None:
    repo = _git_repo(tmp_path / "repo")
    worker = CodexWorker(repo, client=LocalCodexCliClient())
    task = _task(metadata={"codex_mode": "local_cli"})

    result = worker.run(WorkerRequest(task=task, attempt_number=1, structured_input={}))

    assert result.status == AgentResultStatus.NOT_CONFIGURED
    assert result.metadata["codex_mode"] == "local_cli"
    report = MockReviewWorker().review(task, result, 1)
    assert report.decision == ReviewDecision.REJECTED


def test_review_rejects_forbidden_file_violation(tmp_path: Path) -> None:
    repo = _git_repo(tmp_path / "repo")
    worker = CodexWorker(repo, client=MockCodexClient())
    task = _task(metadata={"codex_mode": "mock", "simulate_forbidden_file": True})

    result = worker.run(WorkerRequest(task=task, attempt_number=1, structured_input={}))
    report = MockReviewWorker().review(task, result, 1)

    assert ".github/workflows/verification.yml" in result.metadata["forbidden_file_violations"]
    assert report.decision == ReviewDecision.REJECTED


def test_task_metadata_cannot_clear_system_forbidden_files(tmp_path: Path) -> None:
    repo = _git_repo(tmp_path / "repo")
    worker = CodexWorker(repo, client=MockCodexClient())
    task = _task(
        metadata={
            "codex_mode": "mock",
            "mock_output_file": ".github/workflows/verification.yml",
            "forbidden_files": [],
        }
    )

    result = worker.run(WorkerRequest(task=task, attempt_number=1, structured_input={}))
    report = MockReviewWorker().review(task, result, 1)

    assert ".github/workflows/verification.yml" in result.metadata["forbidden_file_violations"]
    assert report.decision == ReviewDecision.REJECTED


def test_review_rejects_disallowed_completed_command(tmp_path: Path) -> None:
    repo = _git_repo(tmp_path / "repo")
    worker = CodexWorker(repo, client=MaliciousCommandClient())
    task = _task(
        metadata={
            "codex_mode": "test_client",
            "allowed_commands": ["pytest"],
            "forbidden_commands": ["rm"],
        }
    )

    result = worker.run(WorkerRequest(task=task, attempt_number=1, structured_input={}))
    report = MockReviewWorker().review(task, result, 1)

    assert result.metadata["command_violations"] == ["rm -rf workspace"]
    assert result.metadata["command_logs"][0]["allowed"] is False
    assert report.decision == ReviewDecision.REJECTED


def test_review_requires_rework_for_failed_coding_tests(tmp_path: Path) -> None:
    repo = _git_repo(tmp_path / "repo")
    worker = CodexWorker(repo, client=MockCodexClient())
    task = _task(
        metadata={
            "codex_mode": "mock",
            "simulate_test_failure": True,
            "allowed_commands": ["pytest"],
            "required_tests": ["pytest tests/unit/test_codex_worker.py"],
        }
    )

    result = worker.run(WorkerRequest(task=task, attempt_number=1, structured_input={}))
    report = MockReviewWorker().review(task, result, 1)

    assert result.tests_run[0].status == "failed"
    assert report.decision == ReviewDecision.REWORK_REQUIRED


def test_command_log_redacts_sensitive_output(tmp_path: Path) -> None:
    repo = _git_repo(tmp_path / "repo")
    worker = CodexWorker(repo, client=MockCodexClient())
    task = _task(
        metadata={
            "codex_mode": "mock",
            "simulate_secret_output": True,
            "allowed_commands": ["pytest"],
            "required_tests": ["pytest tests/unit/test_codex_worker.py"],
        }
    )

    result = worker.run(WorkerRequest(task=task, attempt_number=1, structured_input={}))
    command_logs = result.metadata["command_logs"]

    assert isinstance(command_logs, list)
    assert command_logs[0]["stdout_summary"] == "[REDACTED]"


def test_prompt_and_diff_artifacts_are_redacted(tmp_path: Path) -> None:
    repo = _git_repo(tmp_path / "repo")
    worker = CodexWorker(repo, client=MockCodexClient())
    task = _task(metadata={"codex_mode": "mock"})
    task = replace(task, objective="Do not store " + "SECRET" + "_VALUE in artifacts")

    result = worker.run(WorkerRequest(task=task, attempt_number=1, structured_input={}))

    artifact_dir = repo / ".ai_org_artifacts" / task.task_id / "attempt-1"
    prompt = (artifact_dir / "prompt.md").read_text(encoding="utf-8")
    diff = (artifact_dir / "diff.patch").read_text(encoding="utf-8")
    assert "SECRET_VALUE" not in prompt
    assert "SECRET_VALUE" not in diff
    assert result.metadata["policy_violations"] == ["diff:secret_pattern_detected"]
    assert all(not artifact.uri.startswith("file:") for artifact in result.artifacts)


def _task(metadata: dict[str, object] | None = None) -> Task:
    return Task(
        task_id="task_codex",
        project_id="proj_codex",
        title="Coding",
        objective="Make a deterministic isolated change",
        worker_type=WorkerType.CODEX.value,
        status=TaskStatus.READY,
        risk_level=RiskLevel.LOW,
        dependencies=[],
        acceptance_criteria=["mock codex reviewed"],
        max_attempts=2,
        metadata=metadata or {},
    )


def _git_repo(path: Path) -> Path:
    path.mkdir()
    _git(path, "init")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "AI Org Test")
    (path / "README.md").write_text("initial\n", encoding="utf-8")
    (path / ".gitignore").write_text(".ai_org_artifacts/\n.ai_org_worktrees/\n", encoding="utf-8")
    _git(path, "add", "README.md", ".gitignore")
    _git(path, "commit", "-m", "initial")
    return path


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=False,
        text=True,
        capture_output=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr)
    return result.stdout


class MaliciousCommandClient:
    def start_task(self, request: CodexTaskRequest) -> CodexTaskResult:
        return CodexTaskResult(
            status=AgentResultStatus.SUCCEEDED,
            summary="Returned a command log with a disallowed completed command.",
            tests_run=[WorkerTestRecord(name="malicious-command-test", status="passed")],
            command_logs=[
                CommandLogEntry(command="rm -rf workspace", status="completed", exit_code=0)
            ],
            metadata={"codex_mode": "test_client"},
        )

    def continue_task(self, request: CodexTaskRequest) -> CodexTaskResult:
        return self.start_task(request)

    def get_status(self, task_id: str) -> str:
        return "completed"

    def collect_result(self, task_id: str) -> CodexTaskResult | None:
        return None

    def cancel_task(self, task_id: str) -> None:
        return None
