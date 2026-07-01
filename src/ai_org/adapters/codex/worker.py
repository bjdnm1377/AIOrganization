from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

from ai_org.adapters.codex.clients import DryRunCodexClient, LocalCodexCliClient, MockCodexClient
from ai_org.adapters.codex.diff import DiffCollector
from ai_org.adapters.codex.logs import CommandLogCollector
from ai_org.adapters.codex.policy import CodingWorkerPolicy
from ai_org.adapters.codex.prompt import CodingTaskPromptRenderer
from ai_org.adapters.codex.worktree import WorktreeService
from ai_org.domain.enums import AgentResultStatus, WorkerType
from ai_org.ports.codex import CodexClient, CodexTaskRequest, CodexTaskResult, CommandLogEntry
from ai_org.ports.sandbox import (
    SandboxCommandResult,
    SandboxCommandSpec,
    SandboxCommandStatus,
    SandboxRunner,
)
from ai_org.ports.workers import Worker, WorkerRequest
from ai_org.protocols.schemas import AgentResult, Artifact


class CodexWorker(Worker):
    worker_type = WorkerType.CODEX.value

    def __init__(
        self,
        repo_root: str | Path,
        client: CodexClient | None = None,
        artifact_root: str | Path | None = None,
        worktree_root: str | Path | None = None,
        sandbox_runner: SandboxRunner | None = None,
    ) -> None:
        root = Path(repo_root).resolve()
        self.worktree_service = WorktreeService(root, worktree_root=worktree_root)
        self.client = client or DryRunCodexClient()
        self.sandbox_runner = sandbox_runner
        self.artifact_root = Path(artifact_root or root / ".ai_org_artifacts").resolve()
        self.diff_collector = DiffCollector(self.artifact_root)
        self.log_collector = CommandLogCollector(self.artifact_root)
        self.prompt_renderer = CodingTaskPromptRenderer()

    @classmethod
    def for_default_mode(cls, repo_root: str | Path) -> CodexWorker:
        return cls(repo_root=repo_root, client=DryRunCodexClient())

    @classmethod
    def for_task_mode(cls, repo_root: str | Path, mode: str) -> CodexWorker:
        client: CodexClient
        if mode == "mock":
            client = MockCodexClient()
        elif mode == "local_cli":
            client = LocalCodexCliClient()
        else:
            client = DryRunCodexClient()
        return cls(repo_root=repo_root, client=client)

    def run(self, request: WorkerRequest) -> AgentResult:
        policy = CodingWorkerPolicy.from_task(request.task)
        context = self.worktree_service.create_worktree(request.task, request.attempt_number)
        prompt = self.prompt_renderer.render(request.task, policy, request.attempt_number)
        prompt_path = self._write_prompt(request.task.task_id, request.attempt_number, prompt)
        sandbox_result = self._run_sandbox_smoke_if_requested(request, context.worktree_path)
        if sandbox_result is not None and sandbox_result.status != SandboxCommandStatus.SUCCEEDED:
            task_result = CodexTaskResult(
                status=AgentResultStatus.FAILED,
                summary="Sandbox preflight blocked the coding task.",
                evidence=["Coding task was not dispatched because sandbox preflight failed."],
                command_logs=[_sandbox_command_log(sandbox_result, _worktree_uri(request))],
                risks=["Sandbox preflight must pass before future code execution."],
                metadata={
                    "codex_mode": policy.mode,
                    "sandbox_enabled": True,
                    "sandbox_status": sandbox_result.status.value,
                    "sandbox_error": sandbox_result.error,
                    "blocked_reason": "SANDBOX_PREFLIGHT_FAILED",
                },
            )
        else:
            sandbox_logs = (
                [_sandbox_command_log(sandbox_result, _worktree_uri(request))]
                if sandbox_result is not None
                else []
            )
            sandbox_metadata = (
                {
                    "sandbox_enabled": True,
                    "sandbox_status": sandbox_result.status.value,
                    "sandbox_image": sandbox_result.image,
                    "sandbox_network_enabled": sandbox_result.network_enabled,
                }
                if sandbox_result is not None
                else {"sandbox_enabled": False}
            )
            client = self._client_for_policy(policy)
            task_result = client.start_task(
                CodexTaskRequest(
                    task=request.task,
                    attempt_number=request.attempt_number,
                    worktree_path=context.worktree_path,
                    prompt=prompt,
                )
            )
            task_result = replace(
                task_result,
                command_logs=[*sandbox_logs, *task_result.command_logs],
                metadata={**task_result.metadata, **sandbox_metadata},
            )
        commands = [
            entry.command
            for entry in task_result.command_logs
            if entry.status not in {"skipped", "not_configured"}
            and not entry.command.startswith("mock.")
            and not entry.command.startswith("sandbox.")
        ]
        command_violations = set(policy.command_violations(commands))
        logical_worktree = _worktree_uri(request)
        command_logs = [
            replace(
                entry,
                cwd=entry.cwd or logical_worktree,
                allowed=entry.command not in command_violations,
            )
            for entry in task_result.command_logs
        ]
        command_log_path, command_payload = self.log_collector.write(
            request.task.task_id, request.attempt_number, command_logs
        )
        diff_path, diff_summary = self.diff_collector.collect(
            context.worktree_path,
            request.task.task_id,
            request.attempt_number,
            policy,
            commands,
        )
        policy_violations = [
            *[f"file:{path}" for path in diff_summary.forbidden_file_violations],
            *[f"command:{command}" for command in diff_summary.command_violations],
        ]
        if diff_summary.secret_patterns_detected:
            policy_violations.append("diff:secret_pattern_detected")
        artifacts = [
            _artifact("codex-prompt", prompt_path, "markdown", request),
            _artifact("codex-command-log", command_log_path, "json", request),
            _artifact("codex-diff", diff_path, "patch", request),
        ]
        metadata: dict[str, object] = {
            **task_result.metadata,
            "coding_worker": True,
            "codex_mode": policy.mode,
            "worktree_path": logical_worktree,
            "worktree_uri": logical_worktree,
            "branch_name": context.branch_name,
            "base_commit": context.base_commit,
            "head_commit": self.worktree_service.head_commit(context.worktree_path),
            "changed_files": diff_summary.changed_files,
            "diff_summary": {
                "changed_files": diff_summary.changed_files,
                "created_files": diff_summary.created_files,
                "deleted_files": diff_summary.deleted_files,
                "binary_files": diff_summary.binary_files,
                "secret_patterns_detected": diff_summary.secret_patterns_detected,
                "truncated": diff_summary.truncated,
                "sha256": diff_summary.sha256,
            },
            "forbidden_file_violations": diff_summary.forbidden_file_violations,
            "command_violations": diff_summary.command_violations,
            "policy_violations": policy_violations,
            "binary_files": diff_summary.binary_files,
            "diff_truncated": diff_summary.truncated,
            "diff_sha256": diff_summary.sha256,
            "tests_run": [record.model_dump(mode="json") for record in task_result.tests_run],
            "command_logs": command_payload,
            "prompt_sha256": _sha256(prompt),
            "no_real_codex_started": task_result.metadata.get(
                "no_real_codex_started", policy.mode != "local_cli"
            ),
            "codex_thread_observed": task_result.metadata.get("codex_thread_observed", False),
            "codex_session_observed": task_result.metadata.get("codex_session_observed", False),
            "blocked_reason": task_result.metadata.get("blocked_reason")
            if task_result.status.value in {"NOT_CONFIGURED", "FAILED"}
            else None,
            "worktree_cleanup": "manual",
        }
        return AgentResult(
            task_id=request.task.task_id,
            status=task_result.status,
            summary=task_result.summary,
            artifacts=artifacts,
            evidence=task_result.evidence,
            tests_run=task_result.tests_run,
            assumptions=task_result.assumptions,
            risks=task_result.risks,
            unresolved_questions=task_result.unresolved_questions,
            metadata=metadata,
        )

    def _client_for_policy(self, policy: CodingWorkerPolicy) -> CodexClient:
        if policy.simulate_not_configured:
            return LocalCodexCliClient()
        if policy.mode == "mock" and not isinstance(self.client, MockCodexClient):
            return MockCodexClient()
        if policy.mode == "local_cli" and not isinstance(self.client, LocalCodexCliClient):
            return LocalCodexCliClient()
        if policy.mode == "dry_run" and not isinstance(self.client, DryRunCodexClient):
            return DryRunCodexClient()
        return self.client

    def _run_sandbox_smoke_if_requested(
        self, request: WorkerRequest, worktree_path: Path
    ) -> SandboxCommandResult | None:
        if self.sandbox_runner is None:
            return None
        if request.task.metadata.get("sandbox_smoke") is not True:
            return None
        return self.sandbox_runner.run(
            SandboxCommandSpec(
                command=("python", "-c", "print('ai-org-sandbox-ok')"),
                worktree_path=worktree_path,
                purpose="codex-worker-sandbox-smoke",
            )
        )

    def _write_prompt(self, task_id: str, attempt_number: int, prompt: str) -> Path:
        directory = self.artifact_root / task_id / f"attempt-{attempt_number}"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "prompt.md"
        path.write_text(prompt, encoding="utf-8")
        return path


def _artifact(name: str, path: Path, kind: str, request: WorkerRequest) -> Artifact:
    data = path.read_bytes()
    return Artifact(
        name=name,
        uri=f"artifact://codex/{request.task.task_id}/attempt-{request.attempt_number}/{path.name}",
        kind=kind,
        sha256=hashlib.sha256(data).hexdigest(),
    )


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _worktree_uri(request: WorkerRequest) -> str:
    return f"worktree://codex/{request.task.task_id}/attempt-{request.attempt_number}"


def _sandbox_command_log(result: SandboxCommandResult, logical_cwd: str) -> CommandLogEntry:
    return CommandLogEntry(
        command="sandbox.health",
        status=result.status.value,
        exit_code=result.exit_code,
        cwd=logical_cwd,
        stdout_summary=result.stdout_summary,
        stderr_summary=result.stderr_summary,
        duration_ms=result.duration_ms,
        timed_out=result.timed_out,
        network_requested=result.network_enabled,
        allowed=result.status == SandboxCommandStatus.SUCCEEDED,
        approval_required=False,
    )
