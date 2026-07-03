from __future__ import annotations

import fnmatch
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from threading import RLock
from uuid import uuid4

from ai_org.domain.enums import ActorType
from ai_org.domain.errors import ConflictError, NotFoundError, ValidationFailure
from ai_org.domain.merge_candidate import (
    MergeCandidate,
    MergeCandidateSourceType,
    MergeCandidateStatus,
    MergeResult,
    MergeResultStatus,
)
from ai_org.domain.models import AuditEvent, utc_now
from ai_org.security import (
    POSIX_ABSOLUTE_PATH_RE,
    WINDOWS_ABSOLUTE_PATH_RE,
    redact,
    sensitive_pattern_count,
)

AuditSink = Callable[[AuditEvent], None]

HIGH_RISK_PATTERNS = (
    ".git/**",
    ".github/**",
    ".env",
    ".env.*",
    "requirements",
    "requirements*",
    "pyproject.toml",
    "alembic/**",
    "scripts/**",
)


class InMemoryPatchArtifactStore:
    def __init__(self) -> None:
        self._lock = RLock()
        self._patches: dict[str, str] = {}

    def add_patch(self, uri: str, patch: str) -> str:
        if not uri.startswith("artifact://"):
            raise ValidationFailure("Patch artifact URI must be logical")
        with self._lock:
            self._patches[uri] = patch
        return uri

    def read_patch(self, uri: str) -> str:
        with self._lock:
            try:
                return self._patches[uri]
            except KeyError as exc:
                raise NotFoundError(f"Patch artifact {uri} not found") from exc


class InMemoryMergeCandidateStore:
    def __init__(self) -> None:
        self._lock = RLock()
        self._candidates: dict[str, MergeCandidate] = {}
        self._worker_run_index: dict[str, str] = {}
        self._results: dict[str, MergeResult] = {}

    def add_candidate(self, candidate: MergeCandidate) -> MergeCandidate:
        with self._lock:
            existing_id = self._worker_run_index.get(candidate.worker_run_id)
            if existing_id:
                return deepcopy(self._candidates[existing_id])
            if candidate.candidate_id in self._candidates:
                raise ConflictError(f"MergeCandidate {candidate.candidate_id} already exists")
            self._candidates[candidate.candidate_id] = deepcopy(candidate)
            self._worker_run_index[candidate.worker_run_id] = candidate.candidate_id
            return deepcopy(candidate)

    def get_candidate(self, candidate_id: str) -> MergeCandidate | None:
        with self._lock:
            candidate = self._candidates.get(candidate_id)
            return deepcopy(candidate) if candidate else None

    def list_candidates(self, project_id: str) -> list[MergeCandidate]:
        with self._lock:
            return [
                deepcopy(candidate)
                for candidate in self._candidates.values()
                if candidate.project_id == project_id
            ]

    def update_candidate(self, candidate: MergeCandidate, expected_version: int) -> MergeCandidate:
        with self._lock:
            current = self._candidates.get(candidate.candidate_id)
            if current is None or current.version != expected_version:
                raise ConflictError("MergeCandidate optimistic lock conflict")
            updated = deepcopy(candidate)
            updated.version = expected_version + 1
            self._candidates[candidate.candidate_id] = updated
            return deepcopy(updated)

    def add_result(self, result: MergeResult) -> MergeResult:
        with self._lock:
            if result.result_id in self._results:
                raise ConflictError(f"MergeResult {result.result_id} already exists")
            self._results[result.result_id] = deepcopy(result)
            return deepcopy(result)

    def get_result(self, result_id: str) -> MergeResult | None:
        with self._lock:
            result = self._results.get(result_id)
            return deepcopy(result) if result else None


class MergeApprovalService:
    def __init__(
        self,
        store: InMemoryMergeCandidateStore,
        audit_sink: AuditSink | None = None,
    ) -> None:
        self.store = store
        self._audit_sink = audit_sink or _noop_audit

    def create_candidate(
        self,
        *,
        project_id: str,
        task_id: str,
        worker_run_id: str,
        source_type: MergeCandidateSourceType,
        base_commit: str,
        changed_files: list[str],
        diff_summary: str,
        patch_artifact_uri: str,
        tests_summary: str,
        review_decision: str,
        candidate_branch: str | None = None,
        worktree_uri: str | None = None,
    ) -> MergeCandidate:
        if not patch_artifact_uri.startswith("artifact://"):
            raise ValidationFailure("MergeCandidate patch artifact must use a logical URI")
        candidate = MergeCandidate(
            candidate_id=f"mc_{uuid4().hex}",
            project_id=project_id,
            task_id=task_id,
            worker_run_id=worker_run_id,
            source_type=source_type,
            base_commit=base_commit,
            changed_files=sorted({_normalize_relative_path(path) for path in changed_files}),
            diff_summary=_safe_summary(diff_summary),
            patch_artifact_uri=patch_artifact_uri,
            tests_summary=_safe_summary(tests_summary),
            review_decision=_safe_summary(review_decision).upper(),
            candidate_branch=candidate_branch,
            worktree_uri=worktree_uri,
        )
        candidate = self.store.add_candidate(candidate)
        self._audit(
            candidate,
            "merge_candidate.waiting_approval",
            {
                "candidate_id": candidate.candidate_id,
                "source_type": candidate.source_type.value,
                "changed_files": candidate.changed_files,
            },
        )
        return candidate

    def get_candidate(self, candidate_id: str) -> MergeCandidate:
        candidate = self.store.get_candidate(candidate_id)
        if candidate is None:
            raise NotFoundError(f"MergeCandidate {candidate_id} not found")
        return candidate

    def list_candidates(self, project_id: str) -> list[MergeCandidate]:
        return self.store.list_candidates(project_id)

    def approve(
        self, candidate_id: str, *, approved_by: str, approval_reason: str
    ) -> MergeCandidate:
        candidate = self.get_candidate(candidate_id)
        self._require_waiting(candidate)
        self._require_approvable(candidate)
        updated = replace(
            candidate,
            status=MergeCandidateStatus.APPROVED,
            approved_at=utc_now(),
            approved_by=_safe_summary(approved_by),
            approval_reason=_safe_summary(approval_reason),
        )
        updated = self.store.update_candidate(updated, expected_version=candidate.version)
        self._audit(
            updated,
            "merge_approval.approved",
            {"candidate_id": candidate_id, "approved_by": updated.approved_by},
        )
        return updated

    def reject(
        self, candidate_id: str, *, rejected_by: str, rejection_reason: str
    ) -> MergeCandidate:
        candidate = self.get_candidate(candidate_id)
        self._require_waiting(candidate)
        updated = replace(
            candidate,
            status=MergeCandidateStatus.REJECTED,
            approved_by=_safe_summary(rejected_by),
            approval_reason=_safe_summary(rejection_reason),
        )
        updated = self.store.update_candidate(updated, expected_version=candidate.version)
        self._audit(
            updated,
            "merge_approval.rejected",
            {"candidate_id": candidate_id, "rejected_by": updated.approved_by},
        )
        return updated

    def block_candidate(self, candidate: MergeCandidate, reason: str) -> MergeCandidate:
        updated = replace(
            candidate,
            status=MergeCandidateStatus.BLOCKED,
            approval_reason=_safe_summary(reason),
        )
        updated = self.store.update_candidate(updated, expected_version=candidate.version)
        self._audit(updated, "merge_candidate.blocked", {"candidate_id": candidate.candidate_id})
        return updated

    def mark_merged(self, candidate: MergeCandidate, result_id: str) -> MergeCandidate:
        updated = replace(candidate, status=MergeCandidateStatus.MERGED)
        updated = self.store.update_candidate(updated, expected_version=candidate.version)
        self._audit(
            updated,
            "merge_candidate.merged",
            {"candidate_id": candidate.candidate_id, "result_id": result_id},
        )
        return updated

    def _require_waiting(self, candidate: MergeCandidate) -> None:
        if candidate.status != MergeCandidateStatus.WAITING_APPROVAL:
            raise ConflictError(f"MergeCandidate is not waiting approval: {candidate.status}")

    def _require_approvable(self, candidate: MergeCandidate) -> None:
        if not candidate.requires_human_merge_approval:
            raise ConflictError("MergeCandidate does not require human merge approval")
        if candidate.auto_merge or candidate.auto_push:
            raise ConflictError("MergeCandidate must not request automatic merge or push")
        if candidate.review_decision != "ACCEPTED":
            raise ConflictError("MergeCandidate has not passed review")
        if candidate.source_type == MergeCandidateSourceType.REAL_CODEX_BLOCKED_FIXTURE:
            raise ConflictError("Blocked real Codex output cannot be approved for merge")

    def _audit(
        self, candidate: MergeCandidate, event_type: str, payload: dict[str, object]
    ) -> None:
        self._audit_sink(
            AuditEvent(
                event_id=f"evt_{uuid4().hex}",
                project_id=candidate.project_id,
                task_id=candidate.task_id,
                event_type=event_type,
                actor_type=ActorType.SYSTEM,
                actor_id="merge-approval-service",
                payload=redact(payload),
            )
        )


class MergeService:
    def __init__(
        self,
        approval_service: MergeApprovalService,
        patch_store: InMemoryPatchArtifactStore,
        audit_sink: AuditSink | None = None,
        repo_path: Path | None = None,
        test_command: list[str] | None = None,
    ) -> None:
        self.approval_service = approval_service
        self.patch_store = patch_store
        self._audit_sink = audit_sink or _noop_audit
        self.repo_path = repo_path
        self.test_command = test_command

    def merge_candidate(
        self,
        candidate_id: str,
        *,
        repo_path: Path | None = None,
        test_command: list[str] | None = None,
    ) -> MergeResult:
        candidate = self.approval_service.get_candidate(candidate_id)
        if candidate.status != MergeCandidateStatus.APPROVED:
            raise ConflictError("Only approved MergeCandidates can enter merge path")
        target_repo = repo_path or self.repo_path
        if target_repo is None:
            raise ConflictError("Merge repository is not configured")
        tests = test_command or self.test_command
        if not tests:
            raise ConflictError("Merge test command is not configured")

        target_repo = target_repo.resolve()
        if _git(target_repo, ["status", "--porcelain=v1"]).strip():
            return self._block(candidate, "MAIN_WORKTREE_DIRTY", tests_passed=False)
        head = _git(target_repo, ["rev-parse", "HEAD"]).strip()
        if head != candidate.base_commit:
            return self._block(candidate, "BASE_CHANGED_BLOCKED", tests_passed=False)
        if _has_forbidden_file(candidate.changed_files):
            return self._block(candidate, "FORBIDDEN_FILE_BLOCKED", tests_passed=False)

        patch = self.patch_store.read_patch(candidate.patch_artifact_uri)
        patch_block = _patch_block_reason(patch)
        if patch_block:
            return self._block(candidate, patch_block, tests_passed=False)
        patch_files = _patch_changed_files(patch)
        if _has_forbidden_file(patch_files):
            return self._block(candidate, "FORBIDDEN_FILE_BLOCKED", tests_passed=False)
        if not patch_files or not set(patch_files).issubset(set(candidate.changed_files)):
            return self._block(candidate, "PATCH_CHANGED_FILES_MISMATCH", tests_passed=False)

        with tempfile.TemporaryDirectory(prefix="ai-org-merge-") as temp:
            integration = Path(temp) / "integration"
            _run_git(None, ["clone", "--no-hardlinks", str(target_repo), str(integration)])
            _run_git(integration, ["checkout", candidate.base_commit])
            apply_result = subprocess.run(
                ["git", "apply", "--whitespace=nowarn", "-"],
                cwd=str(integration),
                input=patch,
                text=True,
                capture_output=True,
                timeout=30,
            )
            if apply_result.returncode != 0:
                return self._block(candidate, "PATCH_APPLY_FAILED", tests_passed=False)
            test_result = subprocess.run(
                tests,
                cwd=str(integration),
                check=False,
                text=True,
                capture_output=True,
                timeout=60,
            )
            if test_result.returncode != 0:
                return self._block(candidate, "MERGE_TESTS_FAILED", tests_passed=False)
            result = MergeResult(
                result_id=f"mr_{uuid4().hex}",
                candidate_id=candidate.candidate_id,
                status=MergeResultStatus.MERGED,
                summary="Patch applied and tests passed in controlled integration clone.",
                tests_passed=True,
                auto_push=False,
                auto_deploy=False,
                integration_worktree_uri="worktree://merge/integration",
            )
        result = self.approval_service.store.add_result(result)
        self.approval_service.mark_merged(candidate, result.result_id)
        self._audit(candidate, "merge_service.merged", result)
        return result

    def _block(self, candidate: MergeCandidate, reason: str, *, tests_passed: bool) -> MergeResult:
        blocked = self.approval_service.block_candidate(candidate, reason)
        result = MergeResult(
            result_id=f"mr_{uuid4().hex}",
            candidate_id=blocked.candidate_id,
            status=MergeResultStatus.BLOCKED,
            summary=reason,
            tests_passed=tests_passed,
            auto_push=False,
            auto_deploy=False,
        )
        result = self.approval_service.store.add_result(result)
        self._audit(blocked, "merge_service.blocked", result)
        return result

    def _audit(self, candidate: MergeCandidate, event_type: str, result: MergeResult) -> None:
        self._audit_sink(
            AuditEvent(
                event_id=f"evt_{uuid4().hex}",
                project_id=candidate.project_id,
                task_id=candidate.task_id,
                event_type=event_type,
                actor_type=ActorType.SYSTEM,
                actor_id="merge-service",
                payload=redact(
                    {
                        "candidate_id": candidate.candidate_id,
                        "result_id": result.result_id,
                        "status": result.status.value,
                        "summary": result.summary,
                        "auto_push": result.auto_push,
                        "auto_deploy": result.auto_deploy,
                    }
                ),
            )
        )


def _normalize_relative_path(path: str) -> str:
    value = path.replace("\\", "/").strip()
    if not value or value.startswith("/") or WINDOWS_ABSOLUTE_PATH_RE.search(value):
        raise ValidationFailure("MergeCandidate changed files must be repository-relative")
    parts = [part for part in value.split("/") if part not in {"", "."}]
    if any(part == ".." for part in parts):
        raise ValidationFailure("MergeCandidate changed files must stay inside repository")
    return "/".join(parts)


def _safe_summary(value: str) -> str:
    return " ".join(str(redact(value)).split())


def _has_forbidden_file(paths: list[str]) -> bool:
    for path in paths:
        normalized = path.replace("\\", "/").strip()
        for pattern in HIGH_RISK_PATTERNS:
            if fnmatch.fnmatch(normalized, pattern):
                return True
    return False


def _patch_block_reason(patch: str) -> str:
    if sensitive_pattern_count(patch):
        return "PATCH_SECRET_BLOCKED"
    if WINDOWS_ABSOLUTE_PATH_RE.search(patch):
        return "PATCH_LOCAL_PATH_BLOCKED"
    cleaned = "\n".join(line for line in patch.splitlines() if "/dev/null" not in line)
    if POSIX_ABSOLUTE_PATH_RE.search(cleaned) or _GENERIC_POSIX_ABSOLUTE_RE.search(cleaned):
        return "PATCH_LOCAL_PATH_BLOCKED"
    return ""


def _patch_changed_files(patch: str) -> list[str]:
    paths: list[str] = []
    for line in patch.splitlines():
        if not line.startswith(("--- ", "+++ ")):
            continue
        value = line[4:].strip()
        if value == "/dev/null":
            continue
        if value.startswith(("a/", "b/")):
            value = value[2:]
        if value:
            paths.append(value)
    return sorted(set(paths))


def _git(cwd: Path, args: list[str]) -> str:
    result = _run_git(cwd, args)
    return result.stdout


def _run_git(cwd: Path | None, args: list[str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd else None,
        check=False,
        text=True,
        capture_output=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise ConflictError(_safe_summary(result.stderr or result.stdout))
    return result


def _noop_audit(event: AuditEvent) -> None:
    return None


_GENERIC_POSIX_ABSOLUTE_RE = re.compile(r"(?m)(?:^|[\s\"'])/(?!dev/null\b)[A-Za-z0-9_.-]+/")
DEFAULT_PYTHON_TEST_COMMAND = [sys.executable, "-m", "pytest", "-q"]
