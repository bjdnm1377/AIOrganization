from __future__ import annotations

import json
from pathlib import Path

from ai_org.ports.codex import CommandLogEntry
from ai_org.security import redact


class CommandLogCollector:
    def __init__(self, artifact_root: str | Path) -> None:
        self.artifact_root = Path(artifact_root).resolve()

    def write(
        self, task_id: str, attempt_number: int, entries: list[CommandLogEntry]
    ) -> tuple[Path, list[dict[str, object]]]:
        directory = self.artifact_root / task_id / f"attempt-{attempt_number}"
        directory.mkdir(parents=True, exist_ok=True)
        payload: list[dict[str, object]] = [
            {
                "command": entry.command,
                "status": entry.status,
                "exit_code": entry.exit_code,
                "cwd": entry.cwd,
                "stdout_summary": _sanitize(entry.stdout_summary),
                "stderr_summary": _sanitize(entry.stderr_summary),
                "duration_ms": entry.duration_ms,
                "timed_out": entry.timed_out,
                "network_requested": entry.network_requested,
                "allowed": entry.allowed,
                "approval_required": entry.approval_required,
                "timeout_type": entry.timeout_type,
                "elapsed_ms": entry.elapsed_ms,
                "jsonl_event_count": entry.jsonl_event_count,
                "jsonl_error_events": entry.jsonl_error_events,
                "jsonl_file_change_events": entry.jsonl_file_change_events,
                "last_jsonl_event_type": entry.last_jsonl_event_type,
                "last_jsonl_event_types": entry.last_jsonl_event_types,
                "approval_requested": entry.approval_requested,
                "timeout_classification": entry.timeout_classification,
                "process_killed": entry.process_killed,
                "process_tree_killed": entry.process_tree_killed,
                "cleanup_error": _sanitize(entry.cleanup_error),
            }
            for entry in entries
        ]
        path = directory / "command-log.json"
        path.write_text(json.dumps(redact(payload), indent=2, sort_keys=True), encoding="utf-8")
        return path, payload


def _sanitize(value: str) -> str:
    redacted = redact(value)
    return redacted if isinstance(redacted, str) else "[REDACTED]"
