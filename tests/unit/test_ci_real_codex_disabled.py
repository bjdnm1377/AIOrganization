from __future__ import annotations

from pathlib import Path


def test_verification_workflow_keeps_real_codex_disabled() -> None:
    workflow = Path(".github/workflows/verification.yml").read_text(encoding="utf-8")

    assert 'AI_ORG_ENABLE_REAL_CODEX_SMOKE: "false"' in workflow
    assert 'AI_ORG_ENABLE_REAL_CODEX_CODE_TASK: "false"' in workflow
    assert 'AI_ORG_ENABLE_REAL_CODEX_MULTI_FILE_TASK: "false"' in workflow
    assert 'AI_ORG_ENABLE_REAL_CODEX_STEPWISE_MULTI_FILE_TASK: "false"' in workflow
    assert 'AI_ORG_ENABLE_REAL_CODEX_DIAGNOSTICS: "false"' in workflow
    assert "tests/unit/test_codex_cli_diagnostics.py" in workflow
    assert "tests/unit/test_merge_approval_service.py" in workflow
    assert "tests/unit/test_merge_service.py" in workflow
    assert "tests/e2e/test_merge_candidates_api.py" in workflow
    assert "tests/manual/test_real_codex_multi_file_task.py" not in workflow
    assert "tests/manual/test_real_codex_stepwise_multi_file_task.py" not in workflow
    assert "tests/manual/test_real_codex_cli_diagnostics.py" not in workflow
    assert "tests/manual/test_real_codex_code_task.py" not in workflow
