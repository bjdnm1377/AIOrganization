from __future__ import annotations

from ai_org.adapters.codex.policy import CodingWorkerPolicy
from ai_org.domain.models import Task
from ai_org.security import redact


class CodingTaskPromptRenderer:
    def render(self, task: Task, policy: CodingWorkerPolicy, attempt_number: int) -> str:
        return "\n".join(
            [
                "# Coding Worker Task",
                f"Task id: {task.task_id}",
                f"Attempt: {attempt_number}",
                f"Title: {_safe_text(task.title)}",
                f"Objective: {_safe_text(task.objective)}",
                "",
                "## Constraints",
                "- Do not call external services outside the configured Codex worker runtime.",
                "- Do not request or use API keys.",
                "- Do not merge, push, or modify the main workspace.",
                "- Work only inside the assigned Git worktree.",
                f"- Allowed files: {', '.join(policy.allowed_files)}",
                f"- Forbidden files: {', '.join(policy.forbidden_files)}",
                f"- Allowed shell commands: {', '.join(policy.allowed_commands) or '<none>'}",
                f"- Required tests: {', '.join(policy.required_tests) or '<none>'}",
                "",
                "## Expected Structured Result",
                "- Summary, artifacts, evidence, tests_run, assumptions, risks,",
                "  unresolved questions.",
            ]
        )


def _safe_text(value: str) -> str:
    redacted = redact(value)
    return redacted if isinstance(redacted, str) else "[REDACTED]"
