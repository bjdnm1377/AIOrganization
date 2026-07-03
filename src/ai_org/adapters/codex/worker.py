from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, replace
from pathlib import Path

from ai_org.adapters.codex.clients import DryRunCodexClient, LocalCodexCliClient, MockCodexClient
from ai_org.adapters.codex.diff import DiffCollector, DiffSummary
from ai_org.adapters.codex.logs import CommandLogCollector
from ai_org.adapters.codex.merge_candidate import MergeCandidateService
from ai_org.adapters.codex.policy import (
    DEFAULT_FORBIDDEN_FILES,
    REAL_STEPWISE_MULTI_FILE_TASK_FORBIDDEN_FILES,
    CodingWorkerPolicy,
)
from ai_org.adapters.codex.prompt import CodingTaskPromptRenderer
from ai_org.adapters.codex.worktree import WorktreeContext, WorktreeService
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

REAL_STEPWISE_MULTI_FILE_TASK_SANDBOX_COMMAND = (
    "python",
    "-m",
    "pytest",
    "tests/unit/test_codex_merge_candidate.py",
    "-q",
)

STEPWISE_TOTAL_TIMEOUT_SECONDS = 540


@dataclass(frozen=True, slots=True)
class StepwiseCodexStepSpec:
    index: int
    name: str
    allowed_file: str
    prompt: str
    extra_forbidden_files: list[str]


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
        elif mode in {
            "local_cli",
            "local_code_task",
            "local_multi_file_task",
            "local_stepwise_multi_file_task",
        }:
            client = LocalCodexCliClient()
        else:
            client = DryRunCodexClient()
        return cls(repo_root=repo_root, client=client)

    def run(self, request: WorkerRequest) -> AgentResult:
        policy = CodingWorkerPolicy.from_task(request.task)
        if policy.mode == "local_stepwise_multi_file_task":
            return self._run_stepwise_multi_file_task(request, policy)
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
        return self._finalize_result(
            request=request,
            policy=policy,
            context=context,
            task_result=task_result,
            prompt_artifacts=[_artifact("codex-prompt", prompt_path, "markdown", request)],
            prompt_sha256=_sha256(prompt),
            main_status_before=main_status_before,
        )

    def _run_stepwise_multi_file_task(
        self, request: WorkerRequest, policy: CodingWorkerPolicy
    ) -> AgentResult:
        context = self.worktree_service.create_worktree(request.task, request.attempt_number)
        main_status_before = self.worktree_service.status_fingerprint()
        steps = _stepwise_merge_candidate_steps()
        logical_prompt = _stepwise_logical_prompt(steps)
        prompt_paths = [
            (
                "codex-prompt",
                self._write_prompt(
                    request.task.task_id,
                    request.attempt_number,
                    logical_prompt,
                ),
            ),
            *[
                (
                    f"codex-step-{step.index}-prompt",
                    self._write_prompt(
                        request.task.task_id,
                        request.attempt_number,
                        step.prompt,
                        filename=f"step-{step.index}-prompt.md",
                    ),
                )
                for step in steps
            ],
        ]
        prompt_artifacts = [
            _artifact(name, path, "markdown", request) for name, path in prompt_paths
        ]
        stepwise_started = time.monotonic()
        client = self._client_for_policy(policy)
        step_records: list[dict[str, object]] = []
        command_logs: list[CommandLogEntry] = []
        tests_run: list[WorkerTestRecord] = []
        evidence: list[str] = []
        risks: list[str] = []
        allowed_so_far: set[str] = set()
        codex_thread_observed = False
        codex_session_observed = False
        external_service_requested = False
        external_service_used = False
        codex_versions: list[str] = []
        final_status = AgentResultStatus.SUCCEEDED
        summary = "Stepwise Codex multi-file task completed in isolated single-file steps."
        blocked_reason: str | None = None
        failed_step_index: int | None = None

        for step in steps:
            step_policy = _step_policy(step)
            step_main_before = self.worktree_service.status_fingerprint()
            step_dirty_before = _dirty_file_snapshot(context.worktree_path)
            step_timeout_seconds = _client_timeout_seconds(client)
            step_task = replace(
                request.task,
                metadata={
                    **request.task.metadata,
                    "codex_mode": "local_stepwise_multi_file_task",
                    "codex_step_index": step.index,
                    "codex_step_allowed_file": step.allowed_file,
                },
            )
            step_result = client.start_task(
                CodexTaskRequest(
                    task=step_task,
                    attempt_number=request.attempt_number,
                    worktree_path=context.worktree_path,
                    prompt=step.prompt,
                )
            )
            step_logs = _step_command_logs(step_result.command_logs)
            command_logs.extend(step_logs)
            tests_run.extend(step_result.tests_run)
            evidence.extend(step_result.evidence)
            risks.extend(step_result.risks)
            codex_thread_observed = codex_thread_observed or bool(
                step_result.metadata.get("codex_thread_observed", False)
            )
            codex_session_observed = codex_session_observed or bool(
                step_result.metadata.get("codex_session_observed", False)
            )
            external_service_requested = external_service_requested or bool(
                step_result.metadata.get("external_service_requested", False)
            )
            external_service_used = external_service_used or bool(
                step_result.metadata.get("external_service_used", False)
            )
            codex_version = step_result.metadata.get("codex_version")
            if isinstance(codex_version, str) and codex_version not in codex_versions:
                codex_versions.append(codex_version)
            step_main_after = self.worktree_service.status_fingerprint()
            step_dirty_after = _dirty_file_snapshot(context.worktree_path)
            modified_files = _snapshot_delta(step_dirty_before, step_dirty_after)
            allowed_so_far.add(step.allowed_file)
            current_changed_files = sorted(step_dirty_after)
            step_file_violations = sorted(
                set(step_policy.file_violations(modified_files))
                | {path for path in current_changed_files if path not in allowed_so_far}
            )
            step_blocked_reason = _step_blocked_reason(step_result)
            step_record: dict[str, object] = {
                "index": step.index,
                "name": step.name,
                "allowed_files": [step.allowed_file],
                "forbidden_files": step.extra_forbidden_files,
                "timeout_seconds": step_timeout_seconds,
                "status": step_result.status.value,
                "blocked_reason": step_blocked_reason,
                "main_worktree_fingerprint_before": step_main_before,
                "main_worktree_fingerprint_after": step_main_after,
                "main_worktree_fingerprint_consistent": step_main_before == step_main_after,
                "modified_files": modified_files,
                "current_changed_files": current_changed_files,
                "file_violations": step_file_violations,
                "command_log_count": len(step_logs),
                "cwd": _worktree_uri(request),
            }
            step_record.update(_timeout_diagnostics(step_logs))
            step_records.append(step_record)

            if step_main_after != step_main_before:
                final_status = AgentResultStatus.FAILED
                blocked_reason = "MAIN_WORKTREE_MODIFIED"
                failed_step_index = step.index
                summary = "Stepwise Codex task modified the main worktree."
                risks.append("Main worktree changed during a stepwise Codex execution step.")
                break
            if step_blocked_reason == "CODEX_STEP_TIMEOUT":
                final_status = AgentResultStatus.FAILED
                blocked_reason = "CODEX_STEP_TIMEOUT"
                failed_step_index = step.index
                summary = "Codex CLI stepwise multi-file task execution timed out."
                break
            if step_result.status != AgentResultStatus.SUCCEEDED:
                final_status = step_result.status
                blocked_reason = step_blocked_reason or "CODEX_STEP_FAILED"
                failed_step_index = step.index
                summary = f"Codex step {step.index} did not complete successfully."
                break
            if step_file_violations:
                final_status = AgentResultStatus.FAILED
                blocked_reason = "CODEX_STEP_FILE_POLICY_VIOLATION"
                failed_step_index = step.index
                summary = f"Codex step {step.index} changed files outside its single-file scope."
                break
            if step.allowed_file not in modified_files:
                final_status = AgentResultStatus.FAILED
                blocked_reason = "CODEX_STEP_NO_ALLOWED_FILE_CHANGE"
                failed_step_index = step.index
                summary = f"Codex step {step.index} did not change its allowed file."
                break
            if time.monotonic() - stepwise_started > STEPWISE_TOTAL_TIMEOUT_SECONDS:
                final_status = AgentResultStatus.FAILED
                blocked_reason = "CODEX_STEP_TIMEOUT"
                failed_step_index = step.index
                summary = "Codex stepwise multi-file task exceeded its total timeout."
                break

        sandbox_metadata: dict[str, object] = {
            "sandbox_enabled": False,
            "sandbox_tests_enabled": False,
        }
        if final_status == AgentResultStatus.SUCCEEDED:
            sandbox_result = self._run_sandbox_tests_if_requested(
                request,
                policy,
                CodexTaskResult(status=final_status, summary=summary),
                context.worktree_path,
            )
            if sandbox_result is not None:
                command_logs.append(
                    _sandbox_command_log(
                        sandbox_result,
                        _worktree_uri(request),
                        command_name="sandbox.test",
                    )
                )
                sandbox_metadata.update(
                    {
                        "sandbox_tests_enabled": True,
                        "sandbox_test_status": sandbox_result.status.value,
                        "sandbox_test_error": sandbox_result.error,
                    }
                )
                tests_run.append(
                    WorkerTestRecord(
                        name=_sandbox_test_name(request.task.metadata.get("sandbox_test_profile")),
                        status="passed"
                        if sandbox_result.status == SandboxCommandStatus.SUCCEEDED
                        else "failed",
                        details=sandbox_result.error or sandbox_result.stdout_summary,
                    )
                )
                if sandbox_result.status != SandboxCommandStatus.SUCCEEDED:
                    final_status = AgentResultStatus.FAILED
                    blocked_reason = "SANDBOX_TEST_FAILED"
                    summary = "Stepwise Codex task failed sandbox validation."
            else:
                sandbox_metadata["sandbox_tests_enabled"] = False

        final_main_status = self.worktree_service.status_fingerprint()
        task_metadata: dict[str, object] = {
            "codex_mode": policy.mode,
            "stepwise_multi_file_task": True,
            "step_count": len(steps),
            "stepwise_steps": step_records,
            "stepwise_total_timeout_seconds": STEPWISE_TOTAL_TIMEOUT_SECONDS,
            "stepwise_total_elapsed_ms": _elapsed_ms(stepwise_started),
            "main_worktree_fingerprint_before": main_status_before,
            "main_worktree_fingerprint_after": final_main_status,
            "main_worktree_fingerprint_consistent": final_main_status == main_status_before,
            "real_codex_started": any(
                entry.status not in {"skipped", "not_configured"} for entry in command_logs
            ),
            "no_real_codex_started": not any(
                entry.status not in {"skipped", "not_configured"} for entry in command_logs
            ),
            "auto_merge": False,
            "auto_push": False,
            "codex_thread_observed": codex_thread_observed,
            "codex_session_observed": codex_session_observed,
            "external_service_requested": external_service_requested,
            "external_service_used": external_service_used,
            "codex_versions": codex_versions,
            **sandbox_metadata,
        }
        if blocked_reason is not None:
            task_metadata["blocked_reason"] = blocked_reason
        if failed_step_index is not None:
            task_metadata["failed_step_index"] = failed_step_index
        if blocked_reason == "MAIN_WORKTREE_MODIFIED":
            task_metadata["main_worktree_modified"] = True
        if blocked_reason == "CODEX_STEP_TIMEOUT":
            task_metadata["timeout_type"] = "CODEX_STEP_TIMEOUT"

        task_result = CodexTaskResult(
            status=final_status,
            summary=summary,
            evidence=evidence
            or ["Each successful Codex step ran in the task worktree with one allowed file."],
            tests_run=tests_run,
            command_logs=command_logs,
            assumptions=[
                "Stepwise orchestration does not merge, commit, or push Codex output.",
                "Each Codex step is constrained to one allowed file and rechecked after execution.",
            ],
            risks=risks,
            unresolved_questions=[],
            metadata=task_metadata,
        )
        return self._finalize_result(
            request=request,
            policy=policy,
            context=context,
            task_result=task_result,
            prompt_artifacts=prompt_artifacts,
            prompt_sha256=_sha256(logical_prompt + "\n".join(step.prompt for step in steps)),
            main_status_before=main_status_before,
        )

    def _finalize_result(
        self,
        *,
        request: WorkerRequest,
        policy: CodingWorkerPolicy,
        context: WorktreeContext,
        task_result: CodexTaskResult,
        prompt_artifacts: list[Artifact],
        prompt_sha256: str,
        main_status_before: str,
    ) -> AgentResult:
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
        step_file_violations: list[str] = []
        raw_steps = task_result.metadata.get("stepwise_steps")
        steps = raw_steps if isinstance(raw_steps, list) else []
        for step in steps:
            if not isinstance(step, dict):
                continue
            raw_file_violations = step.get("file_violations")
            if not isinstance(raw_file_violations, list):
                continue
            for path in raw_file_violations:
                if isinstance(path, str):
                    step_file_violations.append(path)
                    policy_violations.append(f"file:{path}")
        policy_violations = sorted(set(policy_violations))
        forbidden_file_violations = sorted(
            set(diff_summary.forbidden_file_violations) | set(step_file_violations)
        )
        artifacts = [
            *prompt_artifacts,
            _artifact("codex-command-log", command_log_path, "json", request),
            _artifact("codex-diff", diff_path, "patch", request),
        ]
        merge_artifact, merge_metadata = self._merge_candidate_artifact_if_needed(
            request, policy, task_result, diff_summary, context
        )
        if merge_artifact is not None:
            artifacts.append(merge_artifact)
        real_cli_modes = {
            "local_cli",
            "local_code_task",
            "local_multi_file_task",
            "local_stepwise_multi_file_task",
        }
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
            "forbidden_file_violations": forbidden_file_violations,
            "command_violations": diff_summary.command_violations,
            "policy_violations": policy_violations,
            "binary_files": diff_summary.binary_files,
            "diff_truncated": diff_summary.truncated,
            "diff_sha256": diff_summary.sha256,
            "tests_run": [record.model_dump(mode="json") for record in task_result.tests_run],
            "command_logs": command_payload,
            "prompt_sha256": prompt_sha256,
            "no_real_codex_started": task_result.metadata.get(
                "no_real_codex_started",
                policy.mode not in real_cli_modes,
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
        if policy.mode == "local_stepwise_multi_file_task" and not isinstance(
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
        expected_mode: str
        command: tuple[str, ...]
        purpose: str
        if profile == "real_code_task_smoke":
            expected_mode = "local_code_task"
            command = REAL_CODE_TASK_SANDBOX_COMMAND
            purpose = "codex-worker-real-code-task-test"
        elif profile == "real_multi_file_task_merge_candidate":
            expected_mode = "local_multi_file_task"
            command = REAL_MULTI_FILE_TASK_SANDBOX_COMMAND
            purpose = "codex-worker-real-multi-file-task-test"
        elif profile == "real_stepwise_multi_file_task_merge_candidate":
            expected_mode = "local_stepwise_multi_file_task"
            command = REAL_STEPWISE_MULTI_FILE_TASK_SANDBOX_COMMAND
            purpose = "codex-worker-real-stepwise-multi-file-task-test"
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
        context: WorktreeContext,
    ) -> tuple[Artifact | None, dict[str, object]]:
        if (
            policy.mode not in {"local_multi_file_task", "local_stepwise_multi_file_task"}
            or task_result.status != AgentResultStatus.SUCCEEDED
        ):
            return None, {}
        summary = MergeCandidateService().build_summary(
            changed_files=diff_summary.changed_files,
            diff_summary=_diff_summary_text(diff_summary),
            review_decision="pending_review",
            tests_passed=_tests_passed(task_result.tests_run),
        )
        summary.update(
            {
                "task_worktree": _worktree_uri(request),
                "branch_name": context.branch_name,
                "base_commit": context.base_commit,
                "head_state": self.worktree_service.head_commit(context.worktree_path),
                "requires_human_merge_approval": True,
                "auto_merge": False,
                "auto_push": False,
            }
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

    def _write_prompt(
        self, task_id: str, attempt_number: int, prompt: str, *, filename: str = "prompt.md"
    ) -> Path:
        directory = self.artifact_root / task_id / f"attempt-{attempt_number}"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / filename
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
    if profile == "real_stepwise_multi_file_task_merge_candidate":
        return "sandbox-real-stepwise-multi-file-task"
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


def _stepwise_merge_candidate_steps() -> list[StepwiseCodexStepSpec]:
    return [
        StepwiseCodexStepSpec(
            index=1,
            name="merge-candidate-summary-code",
            allowed_file="src/ai_org/adapters/codex/merge_candidate.py",
            extra_forbidden_files=["tests/**"],
            prompt=(
                "Step 1/2.\n"
                "Modify only this file: src/ai_org/adapters/codex/merge_candidate.py.\n"
                "Do not modify any other file.\n"
                "Do not read or output secrets.\n"
                "Do not modify the main branch.\n"
                "Do not merge, commit, or push.\n"
                "Do not explain architecture.\n"
                "Do not implement MergeService.\n"
                "Do not write docs.\n"
                "Do not change config, workflow, or dependencies.\n"
                "Implement pure function build_merge_candidate_summary("
                "changed_files: list[str], diff_summary: str, "
                "review_decision: str, tests_passed: bool) -> dict[str, object].\n"
                "No file I/O, network, shell, or env reads.\n"
                "Complete the allowed file, then stop.\n"
            ),
        ),
        StepwiseCodexStepSpec(
            index=2,
            name="merge-candidate-summary-tests",
            allowed_file="tests/unit/test_codex_merge_candidate.py",
            extra_forbidden_files=["src/**"],
            prompt=(
                "Step 2/2.\n"
                "Modify only this file: tests/unit/test_codex_merge_candidate.py.\n"
                "Do not modify any other file.\n"
                "Do not read or output secrets.\n"
                "Do not modify the main branch.\n"
                "Do not merge, commit, or push.\n"
                "Do not explain architecture.\n"
                "Do not implement MergeService.\n"
                "Do not write docs.\n"
                "Do not change config, workflow, or dependencies.\n"
                "Add tests for build_merge_candidate_summary from "
                "ai_org.adapters.codex.merge_candidate.\n"
                "Cover empty changed_files, multiple changed_files, accepted review, "
                "rejected review, tests_passed true/false, stable sorting, "
                "and no local absolute paths.\n"
                "Do not modify the source function.\n"
                "Complete the allowed file, then stop.\n"
            ),
        ),
    ]


def _stepwise_logical_prompt(steps: list[StepwiseCodexStepSpec]) -> str:
    lines = [
        "Logical stepwise multi-file Codex task.",
        "Run each step as a separate Codex CLI invocation in the task worktree.",
        "Do not merge, commit, or push.",
        "Do not implement MergeService.",
        "Do not expose secrets or local absolute paths.",
        "Allowed step files:",
    ]
    lines.extend(f"- step {step.index}: {step.allowed_file}" for step in steps)
    return "\n".join(lines) + "\n"


def _step_policy(step: StepwiseCodexStepSpec) -> CodingWorkerPolicy:
    return CodingWorkerPolicy(
        mode="local_stepwise_multi_file_task",
        allowed_files=[step.allowed_file],
        forbidden_files=_deduplicate(
            [
                *DEFAULT_FORBIDDEN_FILES,
                *REAL_STEPWISE_MULTI_FILE_TASK_FORBIDDEN_FILES,
                *step.extra_forbidden_files,
            ]
        ),
        allowed_commands=["codex"],
    )


def _step_command_logs(logs: list[CommandLogEntry]) -> list[CommandLogEntry]:
    normalized: list[CommandLogEntry] = []
    for entry in logs:
        if entry.timeout_type == "CODEX_CLI_TIMEOUT":
            normalized.append(replace(entry, timeout_type="CODEX_STEP_TIMEOUT"))
        else:
            normalized.append(entry)
    return normalized


def _step_blocked_reason(result: CodexTaskResult) -> str | None:
    blocked_reason = result.metadata.get("blocked_reason")
    if blocked_reason == "CODEX_CLI_TIMEOUT":
        return "CODEX_STEP_TIMEOUT"
    if any(entry.timeout_type == "CODEX_STEP_TIMEOUT" for entry in result.command_logs):
        return "CODEX_STEP_TIMEOUT"
    return blocked_reason if isinstance(blocked_reason, str) else None


def _timeout_diagnostics(logs: list[CommandLogEntry]) -> dict[str, object]:
    timeout_log = next((entry for entry in reversed(logs) if entry.timed_out), None)
    if timeout_log is None:
        return {}
    return {
        "timeout_type": timeout_log.timeout_type,
        "elapsed_ms": timeout_log.elapsed_ms or timeout_log.duration_ms,
        "jsonl_event_count": timeout_log.jsonl_event_count,
        "last_jsonl_event_type": timeout_log.last_jsonl_event_type,
        "approval_requested": timeout_log.approval_requested,
        "process_killed": timeout_log.process_killed,
        "process_tree_killed": timeout_log.process_tree_killed,
        "cleanup_error": timeout_log.cleanup_error,
    }


def _dirty_file_snapshot(worktree_path: Path) -> dict[str, str]:
    status = _git_output(worktree_path, ["status", "--porcelain=v1", "--untracked-files=all"])
    snapshot: dict[str, str] = {}
    for line in status.splitlines():
        if len(line) < 4:
            continue
        relative = _status_path(line)
        snapshot[relative] = f"{line[:2]}:{_file_fingerprint(worktree_path / relative)}"
    return snapshot


def _snapshot_delta(before: dict[str, str], after: dict[str, str]) -> list[str]:
    return sorted(path for path in set(before) | set(after) if before.get(path) != after.get(path))


def _status_path(line: str) -> str:
    raw = line[3:]
    if " -> " in raw:
        raw = raw.split(" -> ", 1)[1]
    return raw.strip('"').replace("\\", "/")


def _file_fingerprint(path: Path) -> str:
    if path.is_symlink():
        try:
            return f"symlink:{path.readlink()}"
        except OSError as exc:
            return f"symlink-error:{exc}"
    if not path.exists():
        return "<deleted>"
    if not path.is_file():
        return "<not-file>"
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_output(cwd: Path, args: list[str]) -> str:
    import subprocess

    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=False,
        text=True,
        capture_output=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result.stdout


def _deduplicate(values: list[str]) -> list[str]:
    deduplicated: list[str] = []
    for value in values:
        if value not in deduplicated:
            deduplicated.append(value)
    return deduplicated


def _client_timeout_seconds(client: CodexClient) -> int | None:
    value = getattr(client, "timeout_seconds", None)
    return value if isinstance(value, int) else None


def _elapsed_ms(started: float) -> int:
    return max(0, int((time.monotonic() - started) * 1000))


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
