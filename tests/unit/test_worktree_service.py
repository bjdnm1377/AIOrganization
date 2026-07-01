from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from ai_org.adapters.codex.worktree import WorktreeService
from ai_org.domain.enums import RiskLevel, TaskStatus, WorkerType
from ai_org.domain.models import Task


def test_worktree_service_creates_branch_from_current_head(tmp_path: Path) -> None:
    repo = _git_repo(tmp_path / "repo")
    task = _task("task_alpha")
    service = WorktreeService(repo)

    context = service.create_worktree(task, 1)
    try:
        assert context.worktree_path.exists()
        assert context.base_commit == _git(repo, "rev-parse", "HEAD").strip()
        assert (
            _git(context.worktree_path, "branch", "--show-current").strip() == context.branch_name
        )
    finally:
        service.cleanup_worktree(context)


def test_worktree_service_keeps_sanitized_paths_inside_repo(tmp_path: Path) -> None:
    repo = _git_repo(tmp_path / "repo")
    task = _task("../task/escape")
    service = WorktreeService(repo)

    context = service.create_worktree(task, 1)
    try:
        assert context.worktree_path.resolve().is_relative_to(
            (repo / ".ai_org_worktrees").resolve()
        )
    finally:
        service.cleanup_worktree(context)


def test_worktree_service_rejects_symlink_root_outside_repo(tmp_path: Path) -> None:
    repo = _git_repo(tmp_path / "repo")
    outside = tmp_path / "outside"
    outside.mkdir()
    link = repo / ".ai_org_worktrees"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Symlinks are not available in this environment")

    with pytest.raises(ValueError, match="inside the repository"):
        WorktreeService(repo, worktree_root=link)


def _task(task_id: str) -> Task:
    return Task(
        task_id=task_id,
        project_id="proj_alpha",
        title="Coding",
        objective="Make a deterministic mock change",
        worker_type=WorkerType.CODEX.value,
        status=TaskStatus.READY,
        risk_level=RiskLevel.LOW,
        dependencies=[],
        acceptance_criteria=["mock codex reviewed"],
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
