from __future__ import annotations

import subprocess
from pathlib import Path

from ai_org.adapters.codex.clients import MockCodexClient
from ai_org.adapters.codex.worker import CodexWorker
from ai_org.adapters.sandbox import MockSandboxRunner
from ai_org.adapters.sandbox.policy import SandboxPolicyError, validate_sandbox_spec
from ai_org.domain.enums import RiskLevel, TaskStatus, WorkerType
from ai_org.domain.models import Task
from ai_org.ports.sandbox import (
    SandboxCommandSpec,
    SandboxCommandStatus,
    SandboxMount,
    SandboxMountPolicy,
    SandboxNetworkPolicy,
    SandboxPolicy,
    SandboxResourceLimits,
)
from ai_org.ports.workers import WorkerRequest


def test_sandbox_policy_defaults_disable_network(tmp_path: Path) -> None:
    spec = _spec(tmp_path)

    validate_sandbox_spec(spec)

    assert spec.policy.network.enabled is False
    assert spec.policy.privileged is False
    assert spec.policy.cap_drop == ("ALL",)
    assert "no-new-privileges" in spec.policy.security_options
    assert spec.policy.read_only_rootfs is True


def test_sandbox_policy_rejects_privileged(tmp_path: Path) -> None:
    spec = _spec(tmp_path, policy=SandboxPolicy(privileged=True))

    error = _policy_error(spec)

    assert "Privileged" in error


def test_sandbox_policy_rejects_network_until_approval_flow_exists(tmp_path: Path) -> None:
    spec = _spec(tmp_path, policy=SandboxPolicy(network=SandboxNetworkPolicy(enabled=True)))

    error = _policy_error(spec)

    assert "network" in error.lower()


def test_sandbox_policy_rejects_host_mounts(tmp_path: Path) -> None:
    worktree = _worktree(tmp_path)
    policy = SandboxPolicy(
        mounts=SandboxMountPolicy(
            extra_mounts=(SandboxMount(host_path=tmp_path.parent, container_path="/host"),)
        )
    )

    error = _policy_error(
        SandboxCommandSpec(command=("python", "-V"), worktree_path=worktree, policy=policy)
    )

    assert "Only task worktree paths" in error


def test_sandbox_policy_rejects_dotenv_and_credential_mounts(tmp_path: Path) -> None:
    worktree = _worktree(tmp_path)
    dotenv = tmp_path / ".env"
    dotenv.write_text("TOKEN=example\n", encoding="utf-8")
    policy = SandboxPolicy(
        mounts=SandboxMountPolicy(
            extra_mounts=(SandboxMount(host_path=dotenv, container_path="/run/secrets/.env"),)
        )
    )

    error = _policy_error(
        SandboxCommandSpec(command=("python", "-V"), worktree_path=worktree, policy=policy)
    )

    assert "Credential" in error


def test_sandbox_policy_rejects_home_as_primary_worktree() -> None:
    spec = SandboxCommandSpec(command=("python", "-V"), worktree_path=Path.home())

    error = _policy_error(spec)

    assert "home or credential" in error


def test_sandbox_policy_rejects_primary_credential_path(tmp_path: Path) -> None:
    ssh_like = tmp_path / ".ssh"
    ssh_like.mkdir()
    spec = SandboxCommandSpec(command=("python", "-V"), worktree_path=ssh_like)

    error = _policy_error(spec)

    assert "home or credential" in error


def test_sandbox_policy_records_resource_limits(tmp_path: Path) -> None:
    limits = SandboxResourceLimits(
        cpus="0.5",
        memory="256m",
        pids_limit=32,
        timeout_seconds=5,
        stdout_limit_bytes=128,
        stderr_limit_bytes=128,
    )
    spec = _spec(tmp_path, policy=SandboxPolicy(resources=limits))

    validate_sandbox_spec(spec)

    assert spec.policy.resources == limits


def test_mock_sandbox_runner_sanitizes_command_output(tmp_path: Path) -> None:
    runner = MockSandboxRunner()

    result = runner.run(_spec(tmp_path, command=("python", "-c", "print('SECRET_VALUE')")))

    assert result.status == SandboxCommandStatus.SUCCEEDED
    assert result.network_enabled is False
    assert "SECRET" not in result.stdout_summary


def test_mock_sandbox_runner_returns_blocked_when_unavailable(tmp_path: Path) -> None:
    runner = MockSandboxRunner(available=False)

    result = runner.run(_spec(tmp_path))

    assert result.status == SandboxCommandStatus.BLOCKED
    assert result.error == "SANDBOX_BACKEND_UNAVAILABLE"


def test_codex_worker_can_run_optional_sandbox_smoke(tmp_path: Path) -> None:
    repo = _git_repo(tmp_path / "repo")
    sandbox_runner = MockSandboxRunner()
    worker = CodexWorker(repo, client=MockCodexClient(), sandbox_runner=sandbox_runner)
    task = _task(
        metadata={
            "codex_mode": "mock",
            "mock_output_file": "src/generated.txt",
            "allowed_files": ["src/generated.txt"],
            "sandbox_smoke": True,
        }
    )

    result = worker.run(WorkerRequest(task=task, attempt_number=1, structured_input={}))

    assert result.metadata["sandbox_enabled"] is True
    assert result.metadata["sandbox_status"] == SandboxCommandStatus.SUCCEEDED.value
    assert result.metadata["command_logs"][0]["command"] == "sandbox.health"
    assert len(sandbox_runner.requests) == 1


def _spec(
    tmp_path: Path,
    *,
    command: tuple[str, ...] = ("python", "-V"),
    policy: SandboxPolicy | None = None,
) -> SandboxCommandSpec:
    return SandboxCommandSpec(
        command=command,
        worktree_path=_worktree(tmp_path),
        policy=policy or SandboxPolicy(),
    )


def _worktree(tmp_path: Path) -> Path:
    worktree = tmp_path / "worktree"
    worktree.mkdir(exist_ok=True)
    return worktree


def _policy_error(spec: SandboxCommandSpec) -> str:
    try:
        validate_sandbox_spec(spec)
    except SandboxPolicyError as exc:
        return str(exc)
    raise AssertionError("Expected sandbox policy validation to fail.")


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
