"""Fail-closed registry for the governed multi-worker surface."""

from __future__ import annotations

from pathlib import Path
import shutil
import os
from typing import Any, Optional

from nexus.executors.codex_executor import CodexCliExecutor
from nexus.executors.cli_worker import CliWorkerStatus
from nexus.executors.worker_contract import (
    SUPPORTED_WORKER_PROVIDERS,
    WorkerAdapter,
    WorkerExecutionReceipt,
    WorkerOutcome,
    WorkerPreflight,
    WorkerProviderUnavailable,
)


class CodexWorkerAdapter:
    provider = "codex"

    def __init__(self, executor: Optional[CodexCliExecutor] = None):
        self.executor = executor or CodexCliExecutor()

    def preflight(self) -> WorkerPreflight:
        executable = shutil.which(self.executor.executable)
        resolved = str(Path(executable).resolve()) if executable else None
        return WorkerPreflight(
            provider=self.provider,
            executable=resolved,
            executable_available=resolved is not None,
            authorized=resolved is not None,
            implementation_status="IMPLEMENTED",
            ready=resolved is not None,
            reason="ready" if resolved else f"executable not found: {self.executor.executable}",
        )

    def invoke(
        self,
        contract: Any,
        lease: Any,
        *,
        prompt: str,
        timeout_seconds: Optional[float] = None,
        on_process_group: Any = None,
    ) -> WorkerExecutionReceipt:
        executor = self.executor
        if timeout_seconds is not None or on_process_group is not None:
            executor = CodexCliExecutor(
                executable=self.executor.executable,
                timeout_seconds=timeout_seconds or self.executor.timeout_seconds,
                model=self.executor.model,
                on_process_group=on_process_group,
            )
        receipt = executor.invoke(contract, lease, prompt=prompt)
        if receipt.worker_status == CliWorkerStatus.TIMED_OUT.value:
            outcome = WorkerOutcome.INCOMPLETE
        elif receipt.worker_status != CliWorkerStatus.COMPLETED.value or receipt.exit_code != 0:
            outcome = WorkerOutcome.FAILED
        else:
            outcome = WorkerOutcome.PROVEN
        return WorkerExecutionReceipt(
            provider=receipt.provider,
            task_id=receipt.task_id,
            target_worktree=receipt.target_worktree,
            worker_status=receipt.worker_status,
            outcome=outcome.value,
            exit_code=receipt.exit_code,
            executable_identity=receipt.executable_identity,
            argv=receipt.argv,
            stdout_sha256=receipt.stdout_sha256,
            stderr_sha256=receipt.stderr_sha256,
            wall_time_ms=receipt.wall_time_ms,
            process_group_id=receipt.process_group_id,
            process_group_killed=False,
            timed_out=receipt.worker_status == CliWorkerStatus.TIMED_OUT.value,
            provider_calls=receipt.provider_calls,
            evidence_complete=outcome == WorkerOutcome.PROVEN,
            commit_created=receipt.commit_created,
            merge_performed=receipt.merge_performed,
            push_performed=False,
            failure_reason=None if outcome == WorkerOutcome.PROVEN else "Codex execution did not prove a successful run",
        )


class UnimplementedWorkerAdapter:
    def __init__(self, provider: str, executable: str):
        self.provider = provider
        self.executable = executable

    def preflight(self) -> WorkerPreflight:
        resolved = shutil.which(self.executable)
        return WorkerPreflight(
            provider=self.provider,
            executable=str(Path(resolved).resolve()) if resolved else None,
            executable_available=resolved is not None,
            authorized=False,
            implementation_status="UNIMPLEMENTED",
            ready=False,
            reason="provider adapter is not implemented; binary presence is not execution proof",
        )

    def invoke(self, contract: Any, lease: Any, *, prompt: str, **options: Any) -> WorkerExecutionReceipt:
        raise WorkerProviderUnavailable(
            f"{self.provider}: provider adapter is not implemented; refusing execution"
        )


class DirectCliWorkerAdapter:
    """Direct CLI adapter enabled only with explicit external-runtime authorization."""

    def __init__(self, provider: str, executable: str, model_env: str, default_model: str, argv_builder):
        self.provider = provider
        self.executable = executable
        self.model_env = model_env
        self.default_model = default_model
        self.argv_builder = argv_builder

    def preflight(self) -> WorkerPreflight:
        resolved = shutil.which(self.executable)
        authorized = os.getenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "0") == "1"
        if not authorized:
            reason = "NEXUS_EXTERNAL_RUNTIME_AUTHORIZED=1 is required"
        elif resolved is None:
            reason = f"executable not found: {self.executable}"
        else:
            reason = "ready"
        return WorkerPreflight(
            provider=self.provider,
            executable=str(Path(resolved).resolve()) if resolved else None,
            executable_available=resolved is not None,
            authorized=authorized,
            implementation_status="IMPLEMENTED",
            ready=resolved is not None and authorized,
            reason=reason,
        )

    def invoke(
        self,
        contract: Any,
        lease: Any,
        *,
        prompt: str,
        timeout_seconds: Optional[float] = None,
        on_process_group: Any = None,
    ) -> WorkerExecutionReceipt:
        preflight = self.preflight()
        if not preflight.ready:
            raise WorkerProviderUnavailable(f"{self.provider}: {preflight.reason}")
        request = CliWorkerRequest(
            executable=self.executable,
            argv=self.argv_builder(prompt, os.getenv(self.model_env, self.default_model)),
            cwd=str(Path(lease.target_worktree).resolve()),
            timeout_seconds=timeout_seconds or 900.0,
        )
        result = run_cli_worker(request, on_process_group=on_process_group)
        if result.status is CliWorkerStatus.TIMED_OUT:
            outcome = WorkerOutcome.INCOMPLETE
        elif result.status is not CliWorkerStatus.COMPLETED or result.exit_code != 0:
            outcome = WorkerOutcome.FAILED
        else:
            outcome = WorkerOutcome.PROVEN
        return WorkerExecutionReceipt(
            provider=self.provider,
            task_id=contract.task_id,
            target_worktree=str(Path(lease.target_worktree).resolve()),
            worker_status=result.status.value,
            outcome=outcome.value,
            exit_code=result.exit_code,
            executable_identity=result.executable_identity,
            argv=result.argv,
            stdout_sha256=result.stdout_sha256,
            stderr_sha256=result.stderr_sha256,
            wall_time_ms=result.wall_time_ms,
            process_group_id=result.process_group_id,
            process_group_killed=result.process_group_killed,
            timed_out=result.timed_out,
            provider_calls=1,
            evidence_complete=outcome == WorkerOutcome.PROVEN,
            commit_created=False,
            merge_performed=False,
            push_performed=False,
            failure_reason=None if outcome == WorkerOutcome.PROVEN else f"{self.provider} execution did not prove success",
        )


def _gemini_args(prompt: str, model: str) -> tuple[str, ...]:
    return ("--skip-trust", "--approval-mode", "auto_edit", "-m", model, "-p", prompt, "--output-format", "json")


def _opencode_args(prompt: str, model: str) -> tuple[str, ...]:
    return ("run", "--auto", "--model", model, prompt)


def _mimo_args(prompt: str, model: str) -> tuple[str, ...]:
    return ("run", "--never-ask-questions", "--model", model, prompt)


class WorkerRegistry:
    def __init__(self, adapters: dict[str, WorkerAdapter]):
        unknown = set(adapters) - set(SUPPORTED_WORKER_PROVIDERS)
        if unknown:
            raise ValueError(f"unknown worker providers: {sorted(unknown)}")
        missing = set(SUPPORTED_WORKER_PROVIDERS) - set(adapters)
        if missing:
            raise ValueError(f"missing worker providers: {sorted(missing)}")
        self._adapters = dict(adapters)

    @classmethod
    def default(cls) -> "WorkerRegistry":
        return cls(
            {
                "codex": CodexWorkerAdapter(),
                "gemini": DirectCliWorkerAdapter("gemini", "gemini", "NEXUS_GEMINI_WORKER_MODEL", "gemini-2.5-flash", _gemini_args),
                "opencode": DirectCliWorkerAdapter("opencode", "opencode", "NEXUS_OPENCODE_WORKER_MODEL", "opencode/big-pickle", _opencode_args),
                "mimo": DirectCliWorkerAdapter("mimo", "mimo", "NEXUS_MIMO_WORKER_MODEL", "mimo", _mimo_args),
                "ollama": UnimplementedWorkerAdapter("ollama", "ollama"),
            }
        )

    @property
    def providers(self) -> tuple[str, ...]:
        return SUPPORTED_WORKER_PROVIDERS

    def adapter(self, provider: str) -> WorkerAdapter:
        key = str(provider).strip().lower()
        try:
            return self._adapters[key]
        except KeyError as exc:
            raise ValueError(f"unknown worker provider: {provider}") from exc

    def preflight(self, provider: str) -> WorkerPreflight:
        return self.adapter(provider).preflight()

    def invoke(
        self,
        provider: str,
        contract: Any,
        lease: Any,
        *,
        prompt: str,
        **options: Any,
    ) -> WorkerExecutionReceipt:
        preflight = self.preflight(provider)
        if not preflight.ready:
            raise WorkerProviderUnavailable(f"{provider}: {preflight.reason}")
        return self.adapter(provider).invoke(contract, lease, prompt=prompt, **options)
