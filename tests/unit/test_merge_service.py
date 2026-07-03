from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from ai_org.application.merge_approval import (
    InMemoryMergeCandidateStore,
    InMemoryPatchArtifactStore,
    MergeApprovalService,
    MergeService,
)
from ai_org.domain.errors import ConflictError
from ai_org.domain.merge_candidate import (
    MergeCandidate,
    MergeCandidateSourceType,
    MergeCandidateStatus,
    MergeResultStatus,
)
from ai_org.domain.models import AuditEvent


def test_unapproved_and_rejected_candidates_cannot_merge(tmp_path: Path) -> None:
    repo = _git_repo(tmp_path / "repo")
    context = _context(repo, _successful_test_command("merged"))
    patch = _patch_for_readme(repo, "initial\nmerged\n")
    candidate = context.create_candidate(repo, ["README.md"], patch)

    with pytest.raises(ConflictError, match="Only approved"):
        context.merge_service.merge_candidate(candidate.candidate_id)

    rejected = context.approval_service.reject(
        candidate.candidate_id,
        rejected_by="reviewer",
        rejection_reason="not safe",
    )
    assert rejected.status == MergeCandidateStatus.REJECTED
    with pytest.raises(ConflictError, match="Only approved"):
        context.merge_service.merge_candidate(candidate.candidate_id)


def test_approved_candidate_applies_patch_in_integration_clone_only(tmp_path: Path) -> None:
    repo = _git_repo(tmp_path / "repo")
    events: list[AuditEvent] = []
    context = _context(repo, _successful_test_command("merged"), events)
    patch = _patch_for_readme(repo, "initial\nmerged\n")
    candidate = context.create_candidate(repo, ["README.md"], patch)
    context.approval_service.approve(
        candidate.candidate_id,
        approved_by="reviewer",
        approval_reason="safe fixture",
    )

    result = context.merge_service.merge_candidate(candidate.candidate_id)
    stored = context.approval_service.get_candidate(candidate.candidate_id)

    assert result.status == MergeResultStatus.MERGED
    assert result.tests_passed is True
    assert result.auto_push is False
    assert result.auto_deploy is False
    assert stored.status == MergeCandidateStatus.MERGED
    assert _git(repo, "status", "--short") == ""
    assert (repo / "README.md").read_text(encoding="utf-8") == "initial\n"
    assert "merge_service.merged" in {event.event_type for event in events}


def test_base_commit_change_blocks_merge(tmp_path: Path) -> None:
    repo = _git_repo(tmp_path / "repo")
    context = _context(repo, _successful_test_command("merged"))
    patch = _patch_for_readme(repo, "initial\nmerged\n")
    candidate = _approved_candidate(context, repo, ["README.md"], patch)

    (repo / "other.txt").write_text("new base\n", encoding="utf-8")
    _git(repo, "add", "other.txt")
    _git(repo, "commit", "-m", "advance base")

    result = context.merge_service.merge_candidate(candidate.candidate_id)

    assert result.status == MergeResultStatus.BLOCKED
    assert result.summary == "BASE_CHANGED_BLOCKED"
    assert context.approval_service.get_candidate(candidate.candidate_id).status == (
        MergeCandidateStatus.BLOCKED
    )


def test_forbidden_candidate_file_blocks_merge(tmp_path: Path) -> None:
    repo = _git_repo(tmp_path / "repo")
    context = _context(repo, _successful_test_command("merged"))
    patch = _patch_for_readme(repo, "initial\nmerged\n")
    candidate = _approved_candidate(
        context,
        repo,
        [".github/workflows/verification.yml"],
        patch,
    )

    result = context.merge_service.merge_candidate(candidate.candidate_id)

    assert result.status == MergeResultStatus.BLOCKED
    assert result.summary == "FORBIDDEN_FILE_BLOCKED"


def test_patch_with_secret_or_absolute_path_blocks_merge(tmp_path: Path) -> None:
    repo = _git_repo(tmp_path / "repo")
    context = _context(repo, _successful_test_command("merged"))
    secret_candidate = _approved_candidate(
        context,
        repo,
        ["README.md"],
        _patch_for_readme(repo, "initial\nsk-test-secret000\n"),
        worker_run_id="run-secret",
    )

    secret_result = context.merge_service.merge_candidate(secret_candidate.candidate_id)

    assert secret_result.status == MergeResultStatus.BLOCKED
    assert secret_result.summary == "PATCH_SECRET_BLOCKED"

    path_candidate = _approved_candidate(
        context,
        repo,
        ["README.md"],
        _patch_for_readme(repo, "initial\nC:\\Users\\11566\\token.txt\n"),
        worker_run_id="run-path",
    )

    path_result = context.merge_service.merge_candidate(path_candidate.candidate_id)

    assert path_result.status == MergeResultStatus.BLOCKED
    assert path_result.summary == "PATCH_LOCAL_PATH_BLOCKED"


def test_high_risk_patch_file_blocks_merge_even_if_candidate_claims_safe_file(
    tmp_path: Path,
) -> None:
    repo = _git_repo(tmp_path / "repo")
    context = _context(repo, _successful_test_command("merged"))
    candidate = _approved_candidate(
        context,
        repo,
        ["README.md"],
        _new_file_patch(repo, "requirements-dev.txt", "unsafe==1.0\n"),
    )

    result = context.merge_service.merge_candidate(candidate.candidate_id)

    assert result.status == MergeResultStatus.BLOCKED
    assert result.summary == "FORBIDDEN_FILE_BLOCKED"


def test_patch_file_must_match_candidate_changed_files(tmp_path: Path) -> None:
    repo = _git_repo(tmp_path / "repo")
    context = _context(repo, _successful_test_command("merged"))
    candidate = _approved_candidate(
        context,
        repo,
        ["README.md"],
        _new_file_patch(repo, "src/unreviewed.py", "VALUE = 'merged'\n"),
    )

    result = context.merge_service.merge_candidate(candidate.candidate_id)

    assert result.status == MergeResultStatus.BLOCKED
    assert result.summary == "PATCH_CHANGED_FILES_MISMATCH"


def test_test_failure_blocks_merge(tmp_path: Path) -> None:
    repo = _git_repo(tmp_path / "repo")
    context = _context(repo, [sys.executable, "-c", "raise SystemExit(1)"])
    patch = _patch_for_readme(repo, "initial\nmerged\n")
    candidate = _approved_candidate(context, repo, ["README.md"], patch)

    result = context.merge_service.merge_candidate(candidate.candidate_id)

    assert result.status == MergeResultStatus.BLOCKED
    assert result.summary == "MERGE_TESTS_FAILED"
    assert result.tests_passed is False
    assert context.approval_service.get_candidate(candidate.candidate_id).status == (
        MergeCandidateStatus.BLOCKED
    )


class _Context:
    def __init__(
        self,
        approval_service: MergeApprovalService,
        patch_store: InMemoryPatchArtifactStore,
        merge_service: MergeService,
    ) -> None:
        self.approval_service = approval_service
        self.patch_store = patch_store
        self.merge_service = merge_service

    def create_candidate(
        self,
        repo: Path,
        changed_files: list[str],
        patch: str,
        *,
        worker_run_id: str = "run-1",
    ) -> MergeCandidate:
        uri = f"artifact://merge-candidates/{worker_run_id}.patch"
        self.patch_store.add_patch(uri, patch)
        return self.approval_service.create_candidate(
            project_id="project-1",
            task_id="task-1",
            worker_run_id=worker_run_id,
            source_type=MergeCandidateSourceType.MANUAL_FIXTURE,
            base_commit=_git(repo, "rev-parse", "HEAD").strip(),
            changed_files=changed_files,
            diff_summary="fixture patch",
            patch_artifact_uri=uri,
            tests_summary="fixture tests configured",
            review_decision="accepted",
            worktree_uri="worktree://fixture/manual",
        )


def _context(
    repo: Path,
    test_command: list[str],
    events: list[AuditEvent] | None = None,
) -> _Context:
    if events is None:
        events = []
    store = InMemoryMergeCandidateStore()
    patch_store = InMemoryPatchArtifactStore()
    approval_service = MergeApprovalService(store, events.append)
    merge_service = MergeService(
        approval_service,
        patch_store,
        events.append,
        repo_path=repo,
        test_command=test_command,
    )
    return _Context(approval_service, patch_store, merge_service)


def _approved_candidate(
    context: _Context,
    repo: Path,
    changed_files: list[str],
    patch: str,
    *,
    worker_run_id: str = "run-1",
) -> MergeCandidate:
    candidate = context.create_candidate(repo, changed_files, patch, worker_run_id=worker_run_id)
    return context.approval_service.approve(
        candidate.candidate_id,
        approved_by="reviewer",
        approval_reason="safe fixture",
    )


def _git_repo(path: Path) -> Path:
    path.mkdir()
    _git(path, "init")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "AI Org Test")
    (path / "README.md").write_text("initial\n", encoding="utf-8")
    _git(path, "add", "README.md")
    _git(path, "commit", "-m", "initial")
    return path


def _patch_for_readme(repo: Path, new_content: str) -> str:
    readme = repo / "README.md"
    original = readme.read_text(encoding="utf-8")
    try:
        readme.write_text(new_content, encoding="utf-8")
        return _git(repo, "diff", "--", "README.md")
    finally:
        readme.write_text(original, encoding="utf-8")


def _new_file_patch(repo: Path, relative_path: str, content: str) -> str:
    path = repo / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text(content, encoding="utf-8")
        _git(repo, "add", "-N", relative_path)
        return _git(repo, "diff", "--", relative_path)
    finally:
        if path.exists():
            path.unlink()
        _git(repo, "reset", "--", relative_path)


def _successful_test_command(expected_text: str) -> list[str]:
    return [
        sys.executable,
        "-c",
        (
            "from pathlib import Path; "
            f"raise SystemExit(0 if {expected_text!r} in Path('README.md').read_text() else 1)"
        ),
    ]


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
