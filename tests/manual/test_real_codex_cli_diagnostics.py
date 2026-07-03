from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from ai_org.adapters.codex.diagnostics import (
    CodexCliDiagnosticsRunner,
    CodexDiagnosticCommandResult,
    diagnostics_enabled,
    write_diagnostic_report,
)
from ai_org.adapters.codex.worktree import WorktreeService

pytestmark = pytest.mark.manual_codex


@pytest.mark.skipif(
    not diagnostics_enabled(),
    reason="real Codex CLI diagnostics require explicit opt-in",
)
@pytest.mark.skipif(shutil.which("codex") is None, reason="Codex CLI is not installed")
def test_real_codex_cli_minimal_diagnostics(tmp_path: Path) -> None:
    repo_path = Path(__file__).resolve().parents[2]
    main_fingerprint_before = WorktreeService(repo_path).status_fingerprint()
    diagnostic_repo = _diagnostic_repo(tmp_path / "diagnostic_repo")
    runner = CodexCliDiagnosticsRunner()
    results: list[CodexDiagnosticCommandResult] = []
    report_path = repo_path / ".ai_org_artifacts" / "codex-cli-diagnostics" / "latest.json"
    main_fingerprint_after = ""
    main_status_after = ""

    try:
        version = runner.run_version(diagnostic_repo, timeout_seconds=15)
        results.append(version)
        doctor = runner.run_doctor(diagnostic_repo, timeout_seconds=30)
        results.append(doctor)

        read_only_stdin = runner.run_exec(
            scenario="D2-read-only-stdin",
            worktree_path=diagnostic_repo,
            prompt="Reply with exactly OK.",
            prompt_mode="stdin",
            sandbox="read-only",
            timeout_seconds=120,
        )
        results.append(read_only_stdin)

        read_only_argument = runner.run_exec(
            scenario="D4-read-only-argument",
            worktree_path=diagnostic_repo,
            prompt="Reply with exactly OK.",
            prompt_mode="argument",
            sandbox="read-only",
            timeout_seconds=120,
        )
        results.append(read_only_argument)

        single_file = runner.run_exec(
            scenario="D3-single-file-create",
            worktree_path=diagnostic_repo,
            prompt=(
                "Create diagnostic/codex_diag.txt containing exactly "
                "AI_ORG_CODEX_DIAGNOSTIC_OK. Do not modify any other file. Stop."
            ),
            prompt_mode="stdin",
            sandbox="workspace-write",
            timeout_seconds=180,
        )
        results.append(single_file)
    finally:
        main_fingerprint_after = WorktreeService(repo_path).status_fingerprint()
        main_status_after = _git(repo_path, "status", "--short")
        write_diagnostic_report(
            report_path,
            results,
            status=_status_for_results(results),
            main_worktree_fingerprint_before=main_fingerprint_before,
            main_worktree_fingerprint_after=main_fingerprint_after,
            main_worktree_status_after=main_status_after,
        )

    if main_fingerprint_after != main_fingerprint_before or main_status_after:
        pytest.fail("MAIN_WORKTREE_MODIFIED")
    _fail_for_runtime_blockers(results)
    changed_files = _changed_files(diagnostic_repo)
    assert changed_files in {[], ["diagnostic/codex_diag.txt"]}
    if "diagnostic/codex_diag.txt" in changed_files:
        assert (diagnostic_repo / "diagnostic" / "codex_diag.txt").read_text(
            encoding="utf-8"
        ).strip() == "AI_ORG_CODEX_DIAGNOSTIC_OK"
    assert main_fingerprint_after == main_fingerprint_before
    assert main_status_after == ""


def _status_for_results(results: list[CodexDiagnosticCommandResult]) -> str:
    if any(result.status == "not_installed" for result in results):
        return "Status: BLOCKED - CODEX CLI NOT INSTALLED"
    if any(result.auth_required for result in results):
        return "Status: BLOCKED - CODEX CLI AUTH REQUIRED"
    if any(result.timed_out for result in results):
        return "Status: BLOCKED - CODEX CLI DIAGNOSTIC TIMEOUT"
    if results and all(result.status == "completed" for result in results):
        return "Status: VERIFIED COMPLETE FOR CODEX CLI SINGLE-FILE DIAGNOSTIC"
    return "Status: BLOCKED - CODEX CLI DIAGNOSTIC TIMEOUT"


def _fail_for_runtime_blockers(results: list[CodexDiagnosticCommandResult]) -> None:
    not_installed = [result for result in results if result.status == "not_installed"]
    if not_installed:
        pytest.fail("CODEX_CLI_NOT_INSTALLED")
    auth_required = [result for result in results if result.auth_required]
    if auth_required:
        pytest.fail("CODEX_CLI_AUTH_REQUIRED")
    timeouts = [result for result in results if result.timed_out]
    if timeouts:
        scenarios = ", ".join(result.scenario for result in timeouts)
        pytest.fail(f"CODEX_CLI_DIAGNOSTIC_TIMEOUT: {scenarios}")
    failures = [result for result in results if result.status not in {"completed"}]
    if failures:
        summary = ", ".join(f"{result.scenario}:{result.status}" for result in failures)
        pytest.fail(f"CODEX_CLI_DIAGNOSTIC_FAILED: {summary}")


def _diagnostic_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    _git(path, "init")
    _git(path, "config", "user.email", "diagnostic@example.com")
    _git(path, "config", "user.name", "AI Org Diagnostic")
    (path / "README.md").write_text("diagnostic\n", encoding="utf-8")
    _git(path, "add", "README.md")
    _git(path, "commit", "-m", "diagnostic baseline")
    return path


def _changed_files(path: Path) -> list[str]:
    status = _git(path, "status", "--porcelain=v1", "--untracked-files=all")
    files: list[str] = []
    for line in status.splitlines():
        if len(line) >= 4:
            files.append(line[3:].strip('"').replace("\\", "/"))
    return sorted(files)


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
