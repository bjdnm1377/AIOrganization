from __future__ import annotations

import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from ai_org.adapters.codex.clients import DryRunCodexClient, LocalCodexCliClient, MockCodexClient
from ai_org.adapters.codex.policy import CodingWorkerPolicy
from ai_org.adapters.codex.worker import CodexWorker
from ai_org.adapters.sandbox import MockSandboxRunner
from ai_org.adapters.workers.mock import MockReviewWorker
from ai_org.domain.enums import AgentResultStatus, ReviewDecision, RiskLevel, TaskStatus, WorkerType
from ai_org.domain.models import Task
from ai_org.ports.codex import CodexTaskRequest, CodexTaskResult, CommandLogEntry
from ai_org.ports.workers import WorkerRequest
from ai_org.protocols.schemas import WorkerTestRecord
from ai_org.security import redact, sensitive_pattern_count


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
    assert result.metadata["no_real_codex_started"] is True
    assert result.metadata["blocked_reason"] == "REAL_CODEX_SMOKE_OPT_IN_REQUIRED"
    report = MockReviewWorker().review(task, result, 1)
    assert report.decision == ReviewDecision.REJECTED


def test_local_cli_client_reports_missing_cli_when_opted_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AI_ORG_ENABLE_REAL_CODEX_SMOKE", "true")
    repo = _git_repo(tmp_path / "repo")
    worker = CodexWorker(
        repo,
        client=LocalCodexCliClient(command="ai-org-missing-codex-command"),
    )
    task = _task(metadata={"codex_mode": "local_cli"})

    result = worker.run(WorkerRequest(task=task, attempt_number=1, structured_input={}))

    assert result.status == AgentResultStatus.NOT_CONFIGURED
    assert result.metadata["blocked_reason"] == "CODEX_CLI_NOT_INSTALLED"
    assert result.metadata["no_real_codex_started"] is True


def test_local_cli_client_does_not_call_runner_without_opt_in(tmp_path: Path) -> None:
    runner = FakeCodexRunner()
    client = LocalCodexCliClient(runner=runner)
    request = CodexTaskRequest(
        task=_task(metadata={"codex_mode": "local_cli"}),
        attempt_number=1,
        worktree_path=tmp_path,
        prompt="do not run",
    )

    result = client.start_task(request)

    assert result.status == AgentResultStatus.NOT_CONFIGURED
    assert runner.calls == []


def test_local_code_task_client_does_not_call_runner_without_opt_in(tmp_path: Path) -> None:
    runner = FakeCodexRunner()
    client = LocalCodexCliClient(runner=runner)
    request = CodexTaskRequest(
        task=_task(metadata={"codex_mode": "local_code_task"}),
        attempt_number=1,
        worktree_path=tmp_path,
        prompt="do not run",
    )

    result = client.start_task(request)

    assert result.status == AgentResultStatus.NOT_CONFIGURED
    assert result.metadata["codex_mode"] == "local_code_task"
    assert result.metadata["blocked_reason"] == "REAL_CODEX_CODE_TASK_OPT_IN_REQUIRED"
    assert runner.calls == []


def test_local_code_task_client_reports_missing_cli_when_opted_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AI_ORG_ENABLE_REAL_CODEX_CODE_TASK", "true")
    repo = _git_repo(tmp_path / "repo")
    worker = CodexWorker(
        repo,
        client=LocalCodexCliClient(command="ai-org-missing-codex-command"),
    )
    task = _task(metadata={"codex_mode": "local_code_task"})

    result = worker.run(WorkerRequest(task=task, attempt_number=1, structured_input={}))

    assert result.status == AgentResultStatus.NOT_CONFIGURED
    assert result.metadata["codex_mode"] == "local_code_task"
    assert result.metadata["blocked_reason"] == "CODEX_CLI_NOT_INSTALLED"
    assert result.metadata["no_real_codex_started"] is True


def test_local_cli_client_uses_restricted_exec_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AI_ORG_ENABLE_REAL_CODEX_SMOKE", "true")
    runner = FakeCodexRunner()
    client = LocalCodexCliClient(runner=runner)
    request = CodexTaskRequest(
        task=_task(metadata={"codex_mode": "local_cli"}),
        attempt_number=1,
        worktree_path=tmp_path,
        prompt="Create smoke/codex_worker_smoke.txt without sk-test-secret.",
    )

    result = client.start_task(request)

    assert result.status == AgentResultStatus.SUCCEEDED
    exec_call = runner.calls[-1]
    command_value = exec_call["command"]
    assert isinstance(command_value, list)
    assert all(isinstance(part, str) for part in command_value)
    command = [part for part in command_value if isinstance(part, str)]
    assert exec_call["cwd"] == tmp_path
    assert "--sandbox" in command
    assert "workspace-write" in command
    assert "--ask-for-approval" in command
    assert "on-request" in command
    assert "--cd" in command
    assert str(tmp_path) in command
    assert "sk-test-secret" not in " ".join(command)
    logged_exec = result.command_logs[-1]
    assert "<worktree>" in logged_exec.command
    assert str(tmp_path) not in logged_exec.command
    assert logged_exec.cwd == "worktree://codex/task_codex/attempt-1"
    assert "codex_jsonl_events=" in logged_exec.stdout_summary
    assert "thread_id" not in logged_exec.stdout_summary
    assert "session_id" not in logged_exec.stdout_summary
    assert str(tmp_path) not in logged_exec.stdout_summary
    assert str(Path.home()) not in logged_exec.stdout_summary
    assert logged_exec.network_requested is True
    assert result.metadata["no_real_codex_started"] is False
    assert result.metadata["external_service_requested"] is True
    assert result.metadata["external_service_used"] is True
    assert result.metadata["codex_thread_observed"] is True
    assert result.metadata["codex_session_observed"] is True
    assert "auth_status" not in result.metadata
    assert "doctor_status" not in result.metadata
    assert "codex_thread_id" not in result.metadata
    assert "session_id" not in result.metadata


def test_local_code_task_client_uses_restricted_exec_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AI_ORG_ENABLE_REAL_CODEX_CODE_TASK", "true")
    runner = FakeCodexRunner()
    client = LocalCodexCliClient(runner=runner)
    request = CodexTaskRequest(
        task=_task(metadata={"codex_mode": "local_code_task"}),
        attempt_number=1,
        worktree_path=tmp_path,
        prompt="Create only allowed helper and test files without sk-test-secret.",
    )

    result = client.start_task(request)

    assert result.status == AgentResultStatus.SUCCEEDED
    exec_call = runner.calls[-1]
    command_value = exec_call["command"]
    assert isinstance(command_value, list)
    assert all(isinstance(part, str) for part in command_value)
    command = [part for part in command_value if isinstance(part, str)]
    assert exec_call["cwd"] == tmp_path
    assert "--sandbox" in command
    assert "workspace-write" in command
    assert "--ask-for-approval" in command
    assert "on-request" in command
    assert "--cd" in command
    assert str(tmp_path) in command
    assert "sk-test-secret" not in " ".join(command)
    assert result.metadata["codex_mode"] == "local_code_task"
    assert result.metadata["no_real_codex_started"] is False
    assert result.metadata["codex_thread_observed"] is True


def test_local_cli_client_blocks_dangerous_sandbox(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AI_ORG_ENABLE_REAL_CODEX_SMOKE", "true")
    runner = FakeCodexRunner()
    client = LocalCodexCliClient(runner=runner)
    request = CodexTaskRequest(
        task=_task(metadata={"codex_mode": "local_cli", "codex_sandbox": "danger-full-access"}),
        attempt_number=1,
        worktree_path=tmp_path,
        prompt="do not run",
    )

    result = client.start_task(request)

    assert result.status == AgentResultStatus.FAILED
    assert result.metadata["blocked_reason"] == "CODEX_CLI_POLICY_BLOCKED"
    assert runner.calls == []


def test_local_code_task_client_blocks_dangerous_sandbox(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AI_ORG_ENABLE_REAL_CODEX_CODE_TASK", "true")
    runner = FakeCodexRunner()
    client = LocalCodexCliClient(runner=runner)
    request = CodexTaskRequest(
        task=_task(
            metadata={
                "codex_mode": "local_code_task",
                "codex_sandbox": "danger-full-access",
            }
        ),
        attempt_number=1,
        worktree_path=tmp_path,
        prompt="do not run",
    )

    result = client.start_task(request)

    assert result.status == AgentResultStatus.FAILED
    assert result.metadata["blocked_reason"] == "CODEX_CLI_POLICY_BLOCKED"
    assert runner.calls == []


def test_local_cli_client_timeout_is_failed_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AI_ORG_ENABLE_REAL_CODEX_SMOKE", "true")
    runner = FakeCodexRunner(timeout_on_exec=True)
    client = LocalCodexCliClient(runner=runner, timeout_seconds=5)
    request = CodexTaskRequest(
        task=_task(metadata={"codex_mode": "local_cli"}),
        attempt_number=1,
        worktree_path=tmp_path,
        prompt="Create smoke/codex_worker_smoke.txt",
    )

    result = client.start_task(request)

    assert result.status == AgentResultStatus.FAILED
    assert result.metadata["blocked_reason"] == "CODEX_CLI_TIMEOUT"
    assert result.command_logs[-1].timed_out is True


def test_local_cli_client_failed_exec_is_failed_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AI_ORG_ENABLE_REAL_CODEX_SMOKE", "true")
    runner = FakeCodexRunner(exec_returncode=2)
    client = LocalCodexCliClient(runner=runner)
    request = CodexTaskRequest(
        task=_task(metadata={"codex_mode": "local_cli"}),
        attempt_number=1,
        worktree_path=tmp_path,
        prompt="Create smoke/codex_worker_smoke.txt",
    )

    result = client.start_task(request)

    assert result.status == AgentResultStatus.FAILED
    assert result.metadata["blocked_reason"] == "CODEX_CLI_EXECUTION_FAILED"
    assert result.tests_run[0].status == "failed"
    assert str(Path.home()) not in result.command_logs[-1].stderr_summary


def test_local_cli_policy_cannot_widen_smoke_file_scope() -> None:
    policy = CodingWorkerPolicy.from_task(
        _task(metadata={"codex_mode": "local_cli", "allowed_files": ["**"]})
    )

    assert policy.allowed_files == ["smoke/**"]
    assert policy.file_violations(["notes.txt"]) == ["notes.txt"]
    assert policy.file_violations(["smoke/codex_worker_smoke.txt"]) == []


def test_local_code_task_policy_cannot_widen_file_scope() -> None:
    policy = CodingWorkerPolicy.from_task(
        _task(metadata={"codex_mode": "local_code_task", "allowed_files": ["**"]})
    )

    assert policy.allowed_files == [
        "src/ai_org/adapters/codex/smoke_helpers.py",
        "tests/unit/test_codex_smoke_helpers.py",
    ]
    assert policy.file_violations(["src/ai_org/adapters/codex/clients.py"]) == [
        "src/ai_org/adapters/codex/clients.py"
    ]
    assert policy.file_violations(["docs/CODEX_WORKER.md"]) == ["docs/CODEX_WORKER.md"]
    assert policy.file_violations(["src/ai_org/adapters/codex/smoke_helpers.py"]) == []


def test_local_cli_doctor_timeout_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AI_ORG_ENABLE_REAL_CODEX_SMOKE", "true")
    runner = FakeCodexRunner(timeout_on_doctor=True)
    client = LocalCodexCliClient(runner=runner)
    request = CodexTaskRequest(
        task=_task(metadata={"codex_mode": "local_cli"}),
        attempt_number=1,
        worktree_path=tmp_path,
        prompt="Create smoke/codex_worker_smoke.txt",
    )

    result = client.start_task(request)

    assert result.status == AgentResultStatus.NOT_CONFIGURED
    assert result.metadata["blocked_reason"] == "CODEX_CLI_PREFLIGHT_TIMEOUT"
    assert not any("exec" in _joined_command(call) for call in runner.calls)


def test_local_cli_doctor_unparseable_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AI_ORG_ENABLE_REAL_CODEX_SMOKE", "true")
    runner = FakeCodexRunner(doctor_stdout="not json")
    client = LocalCodexCliClient(runner=runner)
    request = CodexTaskRequest(
        task=_task(metadata={"codex_mode": "local_cli"}),
        attempt_number=1,
        worktree_path=tmp_path,
        prompt="Create smoke/codex_worker_smoke.txt",
    )

    result = client.start_task(request)

    assert result.status == AgentResultStatus.NOT_CONFIGURED
    assert result.metadata["blocked_reason"] == "CODEX_CLI_PREFLIGHT_NOT_READY"
    assert not any("exec" in _joined_command(call) for call in runner.calls)


def test_local_cli_doctor_nonzero_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AI_ORG_ENABLE_REAL_CODEX_SMOKE", "true")
    runner = FakeCodexRunner(doctor_returncode=1)
    client = LocalCodexCliClient(runner=runner)
    request = CodexTaskRequest(
        task=_task(metadata={"codex_mode": "local_cli"}),
        attempt_number=1,
        worktree_path=tmp_path,
        prompt="Create smoke/codex_worker_smoke.txt",
    )

    result = client.start_task(request)

    assert result.status == AgentResultStatus.NOT_CONFIGURED
    assert result.metadata["blocked_reason"] == "CODEX_CLI_PREFLIGHT_FAILED"
    assert not any("exec" in _joined_command(call) for call in runner.calls)


def test_review_rejects_forbidden_file_violation(tmp_path: Path) -> None:
    repo = _git_repo(tmp_path / "repo")
    worker = CodexWorker(repo, client=MockCodexClient())
    task = _task(metadata={"codex_mode": "mock", "simulate_forbidden_file": True})

    result = worker.run(WorkerRequest(task=task, attempt_number=1, structured_input={}))
    report = MockReviewWorker().review(task, result, 1)

    assert ".github/workflows/verification.yml" in result.metadata["forbidden_file_violations"]
    assert report.decision == ReviewDecision.REJECTED


def test_review_rejects_local_code_task_forbidden_file_violation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AI_ORG_ENABLE_REAL_CODEX_CODE_TASK", "true")
    repo = _git_repo(tmp_path / "repo")
    worker = CodexWorker(
        repo,
        client=LocalCodexCliClient(runner=FakeCodexRunner(write_forbidden_file=True)),
    )
    task = _task(metadata={"codex_mode": "local_code_task"})

    result = worker.run(WorkerRequest(task=task, attempt_number=1, structured_input={}))
    report = MockReviewWorker().review(task, result, 1)

    assert "docs/forbidden.md" in result.metadata["forbidden_file_violations"]
    assert report.decision == ReviewDecision.REJECTED


def test_codex_worker_records_sandbox_test_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AI_ORG_ENABLE_REAL_CODEX_CODE_TASK", "true")
    repo = _git_repo(tmp_path / "repo")
    sandbox_runner = MockSandboxRunner()
    worker = CodexWorker(
        repo,
        client=LocalCodexCliClient(runner=FakeCodexRunner()),
        sandbox_runner=sandbox_runner,
    )
    task = _task(
        metadata={
            "codex_mode": "local_code_task",
            "sandbox_test_profile": "real_code_task_smoke",
        }
    )

    result = worker.run(WorkerRequest(task=task, attempt_number=1, structured_input={}))

    assert result.metadata["sandbox_tests_enabled"] is True
    assert result.metadata["sandbox_test_status"] == "SUCCEEDED"
    assert result.tests_run[-1].name == "sandbox-real-code-task"
    assert result.tests_run[-1].status == "passed"
    assert result.metadata["command_logs"][-1]["command"] == "sandbox.test"
    assert len(sandbox_runner.requests) == 1
    assert sandbox_runner.requests[0].env == {"PYTHONDONTWRITEBYTECODE": "1"}


def test_codex_worker_does_not_run_code_task_sandbox_test_without_opt_in(
    tmp_path: Path,
) -> None:
    repo = _git_repo(tmp_path / "repo")
    sandbox_runner = MockSandboxRunner()
    worker = CodexWorker(
        repo,
        client=LocalCodexCliClient(runner=FakeCodexRunner()),
        sandbox_runner=sandbox_runner,
    )
    task = _task(
        metadata={
            "codex_mode": "local_code_task",
            "sandbox_test_profile": "real_code_task_smoke",
        }
    )

    result = worker.run(WorkerRequest(task=task, attempt_number=1, structured_input={}))

    assert result.status == AgentResultStatus.NOT_CONFIGURED
    assert result.metadata.get("sandbox_tests_enabled") is None
    assert sandbox_runner.requests == []


def test_codex_worker_does_not_run_code_task_sandbox_test_for_mock_mode(
    tmp_path: Path,
) -> None:
    repo = _git_repo(tmp_path / "repo")
    sandbox_runner = MockSandboxRunner()
    worker = CodexWorker(repo, client=MockCodexClient(), sandbox_runner=sandbox_runner)
    task = _task(
        metadata={
            "codex_mode": "mock",
            "mock_output_file": "src/ai_org/adapters/codex/smoke_helpers.py",
            "allowed_files": ["src/ai_org/adapters/codex/smoke_helpers.py"],
            "sandbox_test_profile": "real_code_task_smoke",
        }
    )

    result = worker.run(WorkerRequest(task=task, attempt_number=1, structured_input={}))

    assert result.status == AgentResultStatus.SUCCEEDED
    assert result.metadata.get("sandbox_tests_enabled") is None
    assert sandbox_runner.requests == []


def test_codex_worker_marks_missing_sandbox_runner_as_failed_test(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AI_ORG_ENABLE_REAL_CODEX_CODE_TASK", "true")
    repo = _git_repo(tmp_path / "repo")
    worker = CodexWorker(repo, client=LocalCodexCliClient(runner=FakeCodexRunner()))
    task = _task(
        metadata={
            "codex_mode": "local_code_task",
            "sandbox_test_profile": "real_code_task_smoke",
        }
    )

    result = worker.run(WorkerRequest(task=task, attempt_number=1, structured_input={}))
    report = MockReviewWorker().review(task, result, 1)

    assert result.metadata["sandbox_test_status"] == "BLOCKED"
    assert result.tests_run[-1].status == "failed"
    assert report.decision == ReviewDecision.REWORK_REQUIRED


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
    fake_pat = "github_pat_" + ("A" * 24)
    absolute_path = "C:\\Users\\Example\\secret.txt"
    task = replace(
        task,
        objective=(
            "Do not store " + "SECRET" + "_VALUE in artifacts; " + fake_pat + "; " + absolute_path
        ),
    )

    result = worker.run(WorkerRequest(task=task, attempt_number=1, structured_input={}))

    artifact_dir = repo / ".ai_org_artifacts" / task.task_id / "attempt-1"
    prompt = (artifact_dir / "prompt.md").read_text(encoding="utf-8")
    diff = (artifact_dir / "diff.patch").read_text(encoding="utf-8")
    assert "SECRET_VALUE" not in prompt
    assert "SECRET_VALUE" not in diff
    assert fake_pat not in prompt
    assert fake_pat not in diff
    assert absolute_path not in prompt
    assert absolute_path not in diff
    assert result.metadata["policy_violations"] == ["diff:secret_pattern_detected"]
    assert all(not artifact.uri.startswith("file:") for artifact in result.artifacts)
    assert result.metadata["worktree_path"].startswith("worktree://")
    assert str(repo) not in str(result.metadata["command_logs"])


def test_redact_masks_paths_and_common_token_shapes() -> None:
    fake_pat = "github_pat_" + ("A" * 24)
    fake_openai_key = "sk-" + ("B" * 24)
    payload = (
        f"path=C:\\Users\\Example\\secret.txt pat={fake_pat} "
        f"key={fake_openai_key} auth=Bearer abcdefgh12345678"
    )

    redacted = redact(payload)

    assert isinstance(redacted, str)
    assert fake_pat not in redacted
    assert fake_openai_key not in redacted
    assert "abcdefgh12345678" not in redacted
    assert "C:\\Users\\Example\\secret.txt" not in redacted
    assert "<path>" in redacted
    assert sensitive_pattern_count(payload) >= 3


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


def _joined_command(call: dict[str, object]) -> str:
    command = call["command"]
    assert isinstance(command, list)
    assert all(isinstance(part, str) for part in command)
    return " ".join(part for part in command if isinstance(part, str))


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


class FakeCodexRunner:
    def __init__(
        self,
        *,
        exec_returncode: int = 0,
        timeout_on_exec: bool = False,
        timeout_on_doctor: bool = False,
        doctor_returncode: int = 0,
        doctor_stdout: str | None = None,
        write_forbidden_file: bool = False,
    ) -> None:
        self.exec_returncode = exec_returncode
        self.timeout_on_exec = timeout_on_exec
        self.timeout_on_doctor = timeout_on_doctor
        self.doctor_returncode = doctor_returncode
        self.doctor_stdout = doctor_stdout
        self.write_forbidden_file = write_forbidden_file
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
        if command == ["codex", "--version"]:
            return subprocess.CompletedProcess(command, 0, stdout="codex-cli 0.test\n", stderr="")
        if command == ["codex", "doctor", "--json"]:
            if self.timeout_on_doctor:
                raise subprocess.TimeoutExpired(command, timeout_seconds)
            return subprocess.CompletedProcess(
                command,
                self.doctor_returncode,
                stdout=self.doctor_stdout
                or (
                    '{"overallStatus":"ok","codexVersion":"0.test",'
                    '"checks":{"auth.credentials":{"status":"ok"}}}'
                ),
                stderr="" if self.doctor_returncode == 0 else "doctor failed",
            )
        if "exec" in command and command[0] == "codex":
            if self.timeout_on_exec:
                raise subprocess.TimeoutExpired(
                    command,
                    timeout_seconds,
                    output="partial stdout",
                    stderr="partial stderr with SECRET_VALUE",
                )
            if self.write_forbidden_file:
                target = cwd / "docs" / "forbidden.md"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("forbidden change\n", encoding="utf-8")
            escaped_path = str(cwd / "smoke" / "escaped.txt").replace("\\", "\\\\")
            return subprocess.CompletedProcess(
                command,
                self.exec_returncode,
                stdout=(
                    '{"type":"session.created","session_id":"sess_test"}\n'
                    '{"type":"thread.started","thread_id":"thread_test"}\n'
                    f'{{"type":"file_change","path":"{cwd / "smoke" / "file.txt"}"}}\n'
                    f'{{"type":"file_change","path":"{escaped_path}"}}\n'
                    f'{{"type":"debug","path":"{Path.home() / ".codex" / "auth.json"}"}}\n'
                ),
                stderr=""
                if self.exec_returncode == 0
                else f"execution failed at {Path.home() / '.codex' / 'auth.json'}",
            )
        raise AssertionError(f"Unexpected command: {command}")
