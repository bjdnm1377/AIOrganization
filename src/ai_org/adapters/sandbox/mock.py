from __future__ import annotations

from ai_org.adapters.sandbox.policy import SandboxPolicyError, validate_sandbox_spec
from ai_org.ports.sandbox import (
    SandboxAuditEvent,
    SandboxCommandResult,
    SandboxCommandSpec,
    SandboxCommandStatus,
)
from ai_org.security import redact


class MockSandboxRunner:
    def __init__(self, *, available: bool = True) -> None:
        self.available = available
        self.requests: list[SandboxCommandSpec] = []

    def is_available(self) -> bool:
        return self.available

    def run(self, spec: SandboxCommandSpec) -> SandboxCommandResult:
        self.requests.append(spec)
        if not self.available:
            return SandboxCommandResult(
                status=SandboxCommandStatus.BLOCKED,
                command=spec.command,
                image=spec.policy.image,
                error="SANDBOX_BACKEND_UNAVAILABLE",
                audit_events=[
                    SandboxAuditEvent(
                        "sandbox.blocked",
                        {"reason": "SANDBOX_BACKEND_UNAVAILABLE", "backend": "mock"},
                    )
                ],
            )
        try:
            validate_sandbox_spec(spec)
        except SandboxPolicyError as exc:
            return SandboxCommandResult(
                status=SandboxCommandStatus.BLOCKED,
                command=spec.command,
                image=spec.policy.image,
                error=str(exc),
                audit_events=[SandboxAuditEvent("sandbox.policy_blocked", {"reason": str(exc)})],
            )
        stdout = _safe_text("mock sandbox ok")
        return SandboxCommandResult(
            status=SandboxCommandStatus.SUCCEEDED,
            command=spec.command,
            exit_code=0,
            stdout_summary=stdout,
            stderr_summary="",
            duration_ms=1,
            timed_out=False,
            network_enabled=spec.policy.network.enabled,
            image=spec.policy.image,
            audit_events=[
                SandboxAuditEvent(
                    "sandbox.command_completed",
                    {
                        "backend": "mock",
                        "purpose": spec.purpose,
                        "network_enabled": spec.policy.network.enabled,
                    },
                )
            ],
        )


def _safe_text(value: str) -> str:
    redacted = redact(value)
    return redacted if isinstance(redacted, str) else "[REDACTED]"
