from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ai_org.domain.models import Task


@dataclass(frozen=True, slots=True)
class WorktreeContext:
    repo_root: Path
    worktree_path: Path
    branch_name: str
    base_commit: str


class WorktreeService:
    def __init__(self, repo_root: str | Path, worktree_root: str | Path | None = None) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.worktree_root = (
            Path(worktree_root).resolve()
            if worktree_root is not None
            else (self.repo_root / ".ai_org_worktrees").resolve()
        )
        if not self._is_relative_to(self.worktree_root, self.repo_root):
            raise ValueError("Worktree root must stay inside the repository")
        if not (self.repo_root / ".git").exists():
            raise ValueError(f"Repository root is not a Git repository: {self.repo_root}")

    def create_worktree(self, task: Task, attempt_number: int) -> WorktreeContext:
        base_commit = self._git(["rev-parse", "HEAD"], cwd=self.repo_root).strip()
        branch_name = self._branch_name(task, attempt_number)
        worktree_path = self._worktree_path(task, attempt_number)
        if worktree_path.exists():
            raise RuntimeError(f"Worktree already exists: {worktree_path}")
        worktree_path.parent.mkdir(parents=True, exist_ok=True)
        self._git(["worktree", "add", "-b", branch_name, str(worktree_path), base_commit])
        return WorktreeContext(
            repo_root=self.repo_root,
            worktree_path=worktree_path,
            branch_name=branch_name,
            base_commit=base_commit,
        )

    def cleanup_worktree(self, context: WorktreeContext) -> None:
        if self._is_relative_to(context.worktree_path.resolve(), self.worktree_root):
            self._git(["worktree", "remove", "--force", str(context.worktree_path)])
            self._git(["branch", "-D", context.branch_name])

    def head_commit(self, worktree_path: Path) -> str:
        return self._git(["rev-parse", "HEAD"], cwd=worktree_path).strip()

    def _worktree_path(self, task: Task, attempt_number: int) -> Path:
        project_slug = _slug(task.project_id)
        task_slug = _slug(task.task_id)
        path = self.worktree_root / project_slug / task_slug / f"attempt-{attempt_number}"
        resolved = path.resolve()
        if not self._is_relative_to(resolved, self.worktree_root):
            raise ValueError("Resolved worktree path escaped the worktree root")
        return resolved

    def _branch_name(self, task: Task, attempt_number: int) -> str:
        return (
            "ai-org/codex/"
            f"{_slug(task.project_id)[-12:]}/{_slug(task.task_id)[-12:]}-{attempt_number}"
        )

    def _git(self, args: list[str], *, cwd: Path | None = None) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=str(cwd or self.repo_root),
            check=False,
            text=True,
            capture_output=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip())
        return result.stdout

    @staticmethod
    def _is_relative_to(path: Path, parent: Path) -> bool:
        try:
            path.relative_to(parent)
        except ValueError:
            return False
        return True


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip(".-")
    return slug or "item"
