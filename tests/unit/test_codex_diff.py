from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from ai_org.adapters.codex.diff import DiffCollector
from ai_org.adapters.codex.policy import CodingWorkerPolicy


def test_diff_collector_rejects_symlink_escaping_worktree(tmp_path: Path) -> None:
    repo = _git_repo(tmp_path / "repo")
    outside = tmp_path / "outside" / "target.txt"
    outside.parent.mkdir()
    outside.write_text("outside\n", encoding="utf-8")
    link = repo / "src" / "escape.txt"
    link.parent.mkdir()
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("Symlinks are not available in this environment")

    _, summary = DiffCollector(tmp_path / "artifacts").collect(
        repo,
        task_id="task_codex",
        attempt_number=1,
        policy=CodingWorkerPolicy(allowed_files=["src/**"], forbidden_files=[]),
        commands=[],
    )

    assert "src/escape.txt" in summary.changed_files
    assert "src/escape.txt" in summary.forbidden_file_violations


def _git_repo(path: Path) -> Path:
    path.mkdir()
    _git(path, "init")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "AI Org Test")
    (path / "README.md").write_text("initial\n", encoding="utf-8")
    _git(path, "add", "README.md")
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
