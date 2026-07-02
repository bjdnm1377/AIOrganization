from __future__ import annotations

from ai_org.adapters.codex.merge_candidate import (
    MergeCandidateService,
    build_merge_candidate_summary,
)


def test_merge_candidate_summary_handles_empty_changed_files() -> None:
    summary = build_merge_candidate_summary([], "no diff", "accepted", True)

    assert summary["changed_files"] == []
    assert summary["changed_file_count"] == 0
    assert summary["merge_performed"] is False
    assert summary["human_approval_required"] is True


def test_merge_candidate_summary_sorts_and_deduplicates_files() -> None:
    summary = build_merge_candidate_summary(
        ["tests/b.py", "src/a.py", "tests/b.py"], "2 files changed", "accepted", True
    )

    assert summary["changed_files"] == ["src/a.py", "tests/b.py"]
    assert summary["changed_file_count"] == 2


def test_merge_candidate_summary_records_rejected_and_failed_tests() -> None:
    summary = build_merge_candidate_summary(["src/a.py"], "needs work", "rejected", False)

    assert summary["review_decision"] == "rejected"
    assert summary["tests_passed"] is False
    assert summary["approval_state"] == "waiting_merge_approval"


def test_merge_candidate_summary_redacts_absolute_local_paths() -> None:
    summary = build_merge_candidate_summary(
        [
            r"C:\Users\Example\secret.py",
            "/home/example/secret.py",
            "../outside.py",
            "src/safe.py",
        ],
        "paths normalized",
        "accepted",
        True,
    )

    assert summary["changed_files"] == ["<redacted-path>", "src/safe.py"]
    assert "C:" not in str(summary)
    assert "/home/example" not in str(summary)
    assert ".." not in str(summary)


def test_merge_candidate_service_is_pure_data_shaping() -> None:
    summary = MergeCandidateService().build_summary(["b.py", "a.py"], "ok", "ACCEPTED", True)

    assert summary == build_merge_candidate_summary(["b.py", "a.py"], "ok", "ACCEPTED", True)
    assert summary["auto_merge"] is False
    assert summary["auto_push"] is False
