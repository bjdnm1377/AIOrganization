from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ai_org.adapters.codex.policy import CodingWorkerPolicy
from ai_org.security import redact, sensitive_pattern_count


@dataclass(frozen=True, slots=True)
class DiffSummary:
    changed_files: list[str]
    created_files: list[str]
    deleted_files: list[str]
    forbidden_file_violations: list[str]
    command_violations: list[str]
    binary_files: list[str]
    secret_patterns_detected: int
    truncated: bool
    sha256: str


class DiffCollector:
    def __init__(self, artifact_root: str | Path, max_diff_chars: int = 200_000) -> None:
        self.artifact_root = Path(artifact_root).resolve()
        self.max_diff_chars = max_diff_chars

    def collect(
        self,
        worktree_path: Path,
        task_id: str,
        attempt_number: int,
        policy: CodingWorkerPolicy,
        commands: list[str],
    ) -> tuple[Path, DiffSummary]:
        self._git(["add", "-N", "--", "."], cwd=worktree_path)
        status = self._git(["status", "--porcelain=v1"], cwd=worktree_path)
        changed_files = _changed_files(status)
        diff = self._git(["diff", "--binary", "HEAD", "--"], cwd=worktree_path)
        numstat = self._git(["diff", "--numstat", "HEAD", "--"], cwd=worktree_path)
        binary_files = _binary_files(numstat)
        artifact_diff = _sanitize_text(diff)
        truncated = len(diff) > self.max_diff_chars
        if truncated:
            artifact_diff = _sanitize_text(diff[: self.max_diff_chars]) + "\n\n[TRUNCATED]\n"
        directory = self.artifact_root / task_id / f"attempt-{attempt_number}"
        directory.mkdir(parents=True, exist_ok=True)
        diff_path = directory / "diff.patch"
        diff_path.write_text(artifact_diff, encoding="utf-8")
        summary = DiffSummary(
            changed_files=changed_files,
            created_files=_created_files(status),
            deleted_files=_deleted_files(status),
            forbidden_file_violations=policy.file_violations(changed_files),
            command_violations=policy.command_violations(commands),
            binary_files=binary_files,
            secret_patterns_detected=_secret_pattern_count(diff),
            truncated=truncated,
            sha256=hashlib.sha256(artifact_diff.encode("utf-8")).hexdigest(),
        )
        return diff_path, summary

    def _git(self, args: list[str], *, cwd: Path) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            check=False,
            text=True,
            capture_output=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip())
        return result.stdout


def _changed_files(status: str) -> list[str]:
    files: list[str] = []
    for line in status.splitlines():
        if len(line) < 4:
            continue
        files.append(_status_path(line))
    return sorted(set(files))


def _created_files(status: str) -> list[str]:
    files = [
        _status_path(line)
        for line in status.splitlines()
        if len(line) >= 4 and (line[:2] == "??" or "A" in line[:2])
    ]
    return sorted(set(files))


def _deleted_files(status: str) -> list[str]:
    files = [
        _status_path(line) for line in status.splitlines() if len(line) >= 4 and "D" in line[:2]
    ]
    return sorted(set(files))


def _status_path(line: str) -> str:
    raw = line[3:]
    if " -> " in raw:
        raw = raw.split(" -> ", 1)[1]
    return raw.strip('"').replace("\\", "/")


def _binary_files(numstat: str) -> list[str]:
    files: list[str] = []
    for line in numstat.splitlines():
        parts = line.split("\t")
        if len(parts) >= 3 and parts[0] == "-" and parts[1] == "-":
            files.append(parts[2].replace("\\", "/"))
    return sorted(set(files))


def _secret_pattern_count(diff: str) -> int:
    return sensitive_pattern_count(diff)


def _sanitize_text(value: str) -> str:
    redacted = redact(value)
    return redacted if isinstance(redacted, str) else "[REDACTED]"
