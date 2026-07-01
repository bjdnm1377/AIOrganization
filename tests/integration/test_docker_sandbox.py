from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from ai_org.adapters.sandbox import DockerSandboxRunner
from ai_org.ports.sandbox import (
    SandboxCommandSpec,
    SandboxCommandStatus,
    SandboxMount,
    SandboxMountPolicy,
    SandboxPolicy,
    SandboxResourceLimits,
)

pytestmark = pytest.mark.docker


def test_docker_sandbox_runs_fixed_safe_command(tmp_path: Path) -> None:
    _require_docker()
    worktree = _worktree(tmp_path)
    runner = DockerSandboxRunner()

    result = runner.run(
        SandboxCommandSpec(
            command=("python", "-c", "print('sandbox-ok')"),
            worktree_path=worktree,
            purpose="docker-sandbox-ci-smoke",
        )
    )

    assert result.status == SandboxCommandStatus.SUCCEEDED
    assert result.exit_code == 0
    assert result.stdout_summary == "sandbox-ok"
    assert result.network_enabled is False
    assert result.error is None


def test_docker_sandbox_blocks_forbidden_mount(tmp_path: Path) -> None:
    _require_docker()
    worktree = _worktree(tmp_path)
    policy = SandboxPolicy(
        mounts=SandboxMountPolicy(
            extra_mounts=(SandboxMount(host_path=tmp_path.parent, container_path="/host"),)
        )
    )
    runner = DockerSandboxRunner()

    result = runner.run(
        SandboxCommandSpec(
            command=("python", "-V"),
            worktree_path=worktree,
            policy=policy,
            purpose="docker-sandbox-forbidden-mount",
        )
    )

    assert result.status == SandboxCommandStatus.BLOCKED
    assert result.error is not None
    assert "Only task worktree paths" in result.error


def test_docker_sandbox_timeout_is_reported(tmp_path: Path) -> None:
    _require_docker()
    worktree = _worktree(tmp_path)
    policy = SandboxPolicy(resources=SandboxResourceLimits(timeout_seconds=1))
    runner = DockerSandboxRunner()

    result = runner.run(
        SandboxCommandSpec(
            command=("python", "-c", "import time; time.sleep(5)"),
            worktree_path=worktree,
            policy=policy,
            purpose="docker-sandbox-timeout",
        )
    )

    assert result.status == SandboxCommandStatus.TIMED_OUT
    assert result.timed_out is True
    assert result.error == "SANDBOX_TIMEOUT"


def test_docker_sandbox_output_limit_is_enforced(tmp_path: Path) -> None:
    _require_docker()
    worktree = _worktree(tmp_path)
    policy = SandboxPolicy(resources=SandboxResourceLimits(stdout_limit_bytes=32))
    runner = DockerSandboxRunner()

    result = runner.run(
        SandboxCommandSpec(
            command=("python", "-c", "print('x' * 2048)"),
            worktree_path=worktree,
            policy=policy,
            purpose="docker-sandbox-output-limit",
        )
    )

    assert result.status == SandboxCommandStatus.FAILED
    assert result.error == "SANDBOX_OUTPUT_LIMIT_EXCEEDED"
    assert "[TRUNCATED]" in result.stdout_summary


def test_docker_sandbox_redacts_output(tmp_path: Path) -> None:
    _require_docker()
    worktree = _worktree(tmp_path)
    runner = DockerSandboxRunner()

    result = runner.run(
        SandboxCommandSpec(
            command=("python", "-c", "print('SECRET_VALUE')"),
            worktree_path=worktree,
            purpose="docker-sandbox-redaction",
        )
    )

    assert result.status == SandboxCommandStatus.SUCCEEDED
    assert "SECRET" not in result.stdout_summary


def _worktree(tmp_path: Path) -> Path:
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    return worktree


def _require_docker() -> None:
    if _docker_available():
        return
    if os.environ.get("CI") == "true" or os.environ.get("GITHUB_ACTIONS") == "true":
        pytest.fail("Docker is required for CI Docker sandbox integration tests.")
    pytest.skip("Docker is not available; Docker sandbox integration tests skipped explicitly.")


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        result = subprocess.run(
            ["docker", "info"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0
