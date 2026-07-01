from __future__ import annotations

from pathlib import Path


def test_domain_does_not_import_frameworks_or_orm() -> None:
    forbidden = ("langgraph", "fastapi", "sqlalchemy", "alembic")
    for file in Path("src/ai_org/domain").glob("*.py"):
        text = file.read_text(encoding="utf-8")
        assert not any(token in text for token in forbidden), file


def test_first_version_does_not_depend_on_excluded_agent_frameworks() -> None:
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    for package in ("openhands", "crewai", "metagpt", "agent-framework", "openai-agents"):
        assert package not in pyproject
