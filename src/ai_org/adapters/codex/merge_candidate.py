from __future__ import annotations

import re
from dataclasses import dataclass

WINDOWS_ABSOLUTE_PATH = re.compile(r"(?i)^[A-Z]:(?:/|\\)")


@dataclass(frozen=True, slots=True)
class MergeCandidateService:
    """Build reviewable merge summaries without touching git state."""

    def build_summary(
        self,
        changed_files: list[str],
        diff_summary: str,
        review_decision: str,
        tests_passed: bool,
    ) -> dict[str, object]:
        return build_merge_candidate_summary(
            changed_files=changed_files,
            diff_summary=diff_summary,
            review_decision=review_decision,
            tests_passed=tests_passed,
        )


def build_merge_candidate_summary(
    changed_files: list[str],
    diff_summary: str,
    review_decision: str,
    tests_passed: bool,
) -> dict[str, object]:
    sanitized_files = sorted(
        {path for raw_path in changed_files if (path := _sanitize_relative_path(raw_path))}
    )
    return {
        "changed_files": sanitized_files,
        "changed_file_count": len(sanitized_files),
        "diff_summary": _safe_text(diff_summary),
        "review_decision": _safe_text(review_decision).lower(),
        "tests_passed": bool(tests_passed),
        "merge_performed": False,
        "auto_merge": False,
        "auto_push": False,
        "human_approval_required": True,
        "approval_state": "waiting_merge_approval",
    }


def _sanitize_relative_path(path: str) -> str | None:
    value = path.replace("\\", "/").strip()
    if not value:
        return None
    if value.startswith("/") or WINDOWS_ABSOLUTE_PATH.match(value):
        return "<redacted-path>"
    parts = [part for part in value.split("/") if part not in {"", "."}]
    if any(part == ".." for part in parts):
        return "<redacted-path>"
    return "/".join(parts) if parts else None


def _safe_text(value: str) -> str:
    return " ".join(str(value).split())
