from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

from ai_org.adapters.codex.clients import DryRunCodexClient, LocalCodexCliClient, MockCodexClient
from ai_org.adapters.codex.diff import DiffCollector, DiffSummary
from ai_org.adapters.codex.logs import CommandLogCollector
from ai_org.adapters.codex.merge_candidate import MergeCandidateService
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
from ai_org.protocols.schemas import AgentResult, Artifact, WorkerTestRecord

REAL_CODE_TASK_SANDBOX_COMMAND = (
    "python",
    "-c",
    (
        "import importlib.util, pathlib, sys; "
        "sys.dont_write_bytecode = True; "
        "helper = pathlib.Path('src/ai_org/adapters/codex/smoke_helpers.py'); "
        "spec = importlib.util.spec_from_file_location('smoke_helpers', helper); "
        "assert spec is not None and spec.loader is not None; "
        "module = importlib.util.module_from_spec(spec); "
        "spec.loader.exec_module(module); "
        "format_smoke_metadata = module.format_smoke_metadata; "
        "assert format_smoke_metadata({'b': 2, 'a': 'x', 'flag': True, 'none': None}) "
        "== 'a=x, b=2, flag=true, none=null'; "
        "assert format_smoke_metadata({}) == '<empty>'; "
        "assert pathlib.Path('tests/unit/test_codex_smoke_helpers.py').exists()"
    ),
)

REAL_MULTI_FILE_TASK_SANDBOX_COMMAND = (
    "python",
    "-c",
    (
        "import importlib.util, pathlib, sys; "
        "sys.dont_write_bytecode = True; "
        "module_path = pathlib.Path('src/ai_org/adapters/codex/merge_candidate.py'); "
        "assert module_path.exists(); "
        "spec = importlib.util.spec_from_file_location('merge_candidate', module_path); "
        "assert spec is not None and spec.loader is not None; "
        "module = importlib.util.module_from_spec(spec); "
        "spec.loader.exec_module(module); "
        "summary = module.build_merge_candidate_summary("
        "['tests/z.py', 'src/a.py'], '2 files changed', 'accepted', True"
        "); "
        "assert summary['changed_files'] == ['src/a.py', 'tests/z.py']; "
        "assert summary['review_decision'] == 'accepted'; "
        "assert summary['tests_passed'] is True; "
        "assert summary['merge_performed'] is False; "
        "assert summary['auto_merge'] is False; "
        "assert summary['auto_push'] is False; "
        "assert getattr(module, 'MERGE_CANDIDATE_MANUAL_TASK_MARKER') "
        "== 'human-approval-only'; "
        "assert pathlib.Path('tests/unit/test_codex_merge_candidate.py').exists(); "
        "test_text = pathlib.Path('tests/unit/test_codex_merge_candidate.py').read_text(); "
        "assert 'MERGE_CANDIDATE_MANUAL_TASK_MARKER' in test_text"
    ),
)


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
        elif mode in {"local_cli", "local_code_task", "local_multi_file_task"}:
            client = LocalCodexCliClient()
        else:
            client = DryRunCodexClient()
        return cls(repo_root=repo_root, client=client)

    def run(self, request: WorkerRequest) -> AgentResult:
        policy = CodingWorkerPolicy.from_task(request.task)
        context = self.worktree_service.create_worktree(request.task, request.attempt_number)
        main_status_before = self.worktree_service.status_fingerprint()
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
            pre_sandbox_logs = (
                [_sandbox_command_log(sandbox_result, _worktree_uri(request))]
                if sandbox_result is not None
                else []
            )
            post_sandbox_logs: list[CommandLogEntry] = []
            sandbox_metadata: dict[str, object] = (
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
            sandbox_test_result = self._run_sandbox_tests_if_requested(
                request, policy, task_result, context.worktree_path
            )
            if sandbox_test_result is not None:
                post_sandbox_logs.append(
                    _sandbox_command_log(
                        sandbox_test_result,
                        _worktree_uri(request),
                        command_name="sandbox.test",
                    )
                )
                sandbox_metadata.update(
                    {
                        "sandbox_tests_enabled": True,
                        "sandbox_test_status": sandbox_test_result.status.value,
                        "sandbox_test_error": sandbox_test_result.error,
                    }
                )
                sandbox_test = WorkerTestRecord(
                    name=_sandbox_test_name(request.task.metadata.get("sandbox_test_profile")),
                    status="passed"
                    if sandbox_test_result.status == SandboxCommandStatus.SUCCEEDED
                    else "failed",
                    details=sandbox_test_result.error or sandbox_test_result.stdout_summary,
                )
                task_result = replace(
                    task_result,
                    tests_run=[*task_result.tests_run, sandbox_test],
                )
            task_result = replace(
                task_result,
                command_logs=[
                    *pre_sandbox_logs,
                    *task_result.command_logs,
                    *post_sandbox_logs,
                ],
                metadata={**task_result.metadata, **sandbox_metadata},
            )
        main_status_after = self.worktree_service.status_fingerprint()
        if main_status_after != main_status_before:
            task_result = replace(
                task_result,
                status=AgentResultStatus.FAILED,
                summary="Coding task modified the main worktree outside the task worktree.",
                risks=[
                    *task_result.risks,
                    "Main worktree changed during isolated Codex execution.",
                ],
                metadata={
                    **task_result.metadata,
                    "main_worktree_modified": True,
                    "blocked_reason": "MAIN_WORKTREE_MODIFIED",
                },
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
        if task_result.metadata.get("main_worktree_modified") is True:
            policy_violations.append("main_worktree:modified")
        artifacts = [
            _artifact("codex-prompt", prompt_path, "markdown", request),
            _artifact("codex-command-log", command_log_path, "json", request),
            _artifact("codex-diff", diff_path, "patch", request),
        ]
        merge_artifact, merge_metadata = self._merge_candidate_artifact_if_needed(
            request, policy, task_result, diff_summary
        )
        if merge_artifact is not None:
            artifacts.append(merge_artifact)
        metadata: dict[str, object] = {
            **task_result.metadata,
            **merge_metadata,
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
                "no_real_codex_started",
                policy.mode not in {"local_cli", "local_code_task", "local_multi_file_task"},
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
        if policy.mode == "local_code_task" and not isinstance(self.client, LocalCodexCliClient):
            return LocalCodexCliClient()
        if policy.mode == "local_multi_file_task" and not isinstance(
            self.client, LocalCodexCliClient
        ):
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

    def _run_sandbox_tests_if_requested(
        self,
        request: WorkerRequest,
        policy: CodingWorkerPolicy,
        task_result: CodexTaskResult,
        worktree_path: Path,
    ) -> SandboxCommandResult | None:
        profile = request.task.metadata.get("sandbox_test_profile")
        if profile == "real_code_task_smoke":
            expected_mode = "local_code_task"
            command = REAL_CODE_TASK_SANDBOX_COMMAND
            purpose = "codex-worker-real-code-task-test"
        elif profile == "real_multi_file_task_merge_candidate":
            expected_mode = "local_multi_file_task"
            command = REAL_MULTI_FILE_TASK_SANDBOX_COMMAND
            purpose = "codex-worker-real-multi-file-task-test"
        else:
            return None
        if policy.mode != expected_mode or task_result.status != AgentResultStatus.SUCCEEDED:
            return None
        if self.sandbox_runner is None:
            return SandboxCommandResult(
                status=SandboxCommandStatus.BLOCKED,
                command=("sandbox", "test"),
                error="SANDBOX_RUNNER_NOT_CONFIGURED",
            )
        return self.sandbox_runner.run(
            SandboxCommandSpec(
                command=command,
                worktree_path=worktree_path,
                env={"PYTHONDONTWRITEBYTECODE": "1"},
                purpose=purpose,
            )
        )

    def _merge_candidate_artifact_if_needed(
        self,
        request: WorkerRequest,
        policy: CodingWorkerPolicy,
        task_result: CodexTaskResult,
        diff_summary: DiffSummary,
    ) -> tuple[Artifact | None, dict[str, object]]:
        if (
            policy.mode != "local_multi_file_task"
            or task_result.status != AgentResultStatus.SUCCEEDED
        ):
            return None, {}
        summary = MergeCandidateService().build_summary(
            changed_files=diff_summary.changed_files,
            diff_summary=_diff_summary_text(diff_summary),
            review_decision="pending_review",
            tests_passed=_tests_passed(task_result.tests_run),
        )
        directory = self.artifact_root / request.task.task_id / f"attempt-{request.attempt_number}"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "merge-candidate.json"
        path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
        artifact = _artifact("merge-candidate", path, "json", request)
        return artifact, {
            "merge_candidate": summary,
            "merge_candidate_artifact_uri": artifact.uri,
            "merge_candidate_status": "WAITING_MERGE_APPROVAL",
        }

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


def _sandbox_test_name(profile: object) -> str:
    if profile == "real_multi_file_task_merge_candidate":
        return "sandbox-real-multi-file-task"
    return "sandbox-real-code-task"


def _diff_summary_text(diff_summary: DiffSummary) -> str:
    return (
        f"changed={len(diff_summary.changed_files)}; "
        f"created={len(diff_summary.created_files)}; "
        f"deleted={len(diff_summary.deleted_files)}; "
        f"binary={len(diff_summary.binary_files)}; "
        f"truncated={diff_summary.truncated}; "
        f"sha256={diff_summary.sha256}"
    )


def _tests_passed(records: list[WorkerTestRecord]) -> bool:
    return bool(records) and all(record.status in {"passed", "skipped"} for record in records)


def _worktree_uri(request: WorkerRequest) -> str:
    return f"worktree://codex/{request.task.task_id}/attempt-{request.attempt_number}"


def _sandbox_command_log(
    result: SandboxCommandResult, logical_cwd: str, *, command_name: str = "sandbox.health"
) -> CommandLogEntry:
    return CommandLogEntry(
        command=command_name,
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
