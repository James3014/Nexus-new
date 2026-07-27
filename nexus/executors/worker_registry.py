"""Fail-closed registry for the governed multi-worker surface."""

from __future__ import annotations

from pathlib import Path
import shutil
import os
import subprocess
from typing import Any, Optional

from nexus.executors.codex_executor import CodexCliExecutor
from nexus.executors.cli_worker import CliWorkerStatus, CliWorkerRequest, run_cli_worker
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


class AgyWorkerAdapter:
    """Governed Antigravity CLI adapter with explicit external-runtime gates."""

    provider = "agy"

    def __init__(
        self,
        executable_env: str = "NEXUS_AGY_EXECUTABLE",
        project_id_env: str = "NEXUS_AGY_PROJECT_ID",
        model_env: str = "NEXUS_AGY_WORKER_MODEL",
        default_model: str = "gemini-3.6-flash-medium",
    ):
        self.executable_env = executable_env
        self.project_id_env = project_id_env
        self.model_env = model_env
        self.default_model = default_model

    def _configured_executable(self) -> str:
        configured = os.getenv(self.executable_env, "").strip()
        if configured:
            return str(Path(configured).expanduser())
        return str(Path.home() / ".local/bin/agy")

    def _project_id(self) -> str:
        return os.getenv(self.project_id_env, "").strip()

    def _model(self) -> str:
        return os.getenv(self.model_env, self.default_model).strip() or self.default_model

    @staticmethod
    def _timeout_arg(timeout_seconds: float) -> str:
        return str(int(timeout_seconds)) if float(timeout_seconds).is_integer() else str(timeout_seconds)

    def preflight(self) -> WorkerPreflight:
        executable = self._configured_executable()
        resolved = shutil.which(executable)
        authorized = os.getenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "0") == "1"
        project_id = self._project_id()
        if not authorized:
            reason = "NEXUS_EXTERNAL_RUNTIME_AUTHORIZED=1 is required"
        elif not project_id:
            reason = f"{self.project_id_env} is required"
        elif resolved is None:
            reason = f"executable not found: {executable}"
        else:
            reason = "ready"
        return WorkerPreflight(
            provider=self.provider,
            executable=str(Path(resolved).resolve()) if resolved else None,
            executable_available=resolved is not None,
            authorized=authorized,
            implementation_status="IMPLEMENTED",
            ready=resolved is not None and authorized and bool(project_id),
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
        target = str(Path(lease.target_worktree).resolve())
        timeout = timeout_seconds or 900.0
        request = CliWorkerRequest(
            executable=preflight.executable or self._configured_executable(),
            argv=(
                "--project",
                self._project_id(),
                "--add-dir",
                target,
                "--dangerously-skip-permissions",
                "--mode",
                "accept-edits",
                "--model",
                self._model(),
                "--print-timeout",
                self._timeout_arg(timeout),
                "--print",
                prompt,
            ),
            cwd=target,
            timeout_seconds=timeout,
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
            target_worktree=target,
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


class OllamaPatchWorkerAdapter:
    """Local Ollama worker using a governed unified-diff output contract."""

    provider = "ollama"

    def __init__(self, executable: str = "ollama", model_env: str = "NEXUS_OLLAMA_WORKER_MODEL"):
        self.executable = executable
        self.model_env = model_env

    def preflight(self) -> WorkerPreflight:
        resolved = shutil.which(self.executable)
        authorized = os.getenv("NEXUS_LOCAL_MODEL_CALL_ALLOWED", "0") == "1"
        if not authorized:
            reason = "NEXUS_LOCAL_MODEL_CALL_ALLOWED=1 is required"
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

    @staticmethod
    def _extract_patch(stdout: bytes) -> Optional[bytes]:
        marker = b"diff --git "
        index = stdout.find(marker)
        if index < 0:
            return None
        patch = stdout[index:]
        return patch if b"\n" in patch else None

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
        model = os.getenv(self.model_env, "qwen2.5-coder:7b")
        request = CliWorkerRequest(
            executable=self.executable,
            argv=("run", model, prompt + "\nReturn only a unified git diff beginning with diff --git."),
            cwd=str(Path(lease.target_worktree).resolve()),
            timeout_seconds=timeout_seconds or 900.0,
        )
        result = run_cli_worker(request, on_process_group=on_process_group)
        patch = self._extract_patch(result.stdout)
        applied = False
        failure_reason = None
        if result.status is CliWorkerStatus.COMPLETED and result.exit_code == 0 and patch:
            target = str(Path(lease.target_worktree).resolve())
            check = subprocess.run(
                ["git", "apply", "--check", "--binary", "--whitespace=nowarn", "-"],
                cwd=target,
                input=patch,
                capture_output=True,
            )
            if check.returncode == 0:
                applied_result = subprocess.run(
                    ["git", "apply", "--binary", "--whitespace=nowarn", "-"],
                    cwd=target,
                    input=patch,
                    capture_output=True,
                )
                applied = applied_result.returncode == 0
                if not applied:
                    failure_reason = applied_result.stderr.decode("utf-8", errors="replace")
            else:
                failure_reason = check.stderr.decode("utf-8", errors="replace")
        else:
            failure_reason = "Ollama did not return a usable unified diff"
        outcome = WorkerOutcome.PROVEN if applied else WorkerOutcome.FAILED
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
            evidence_complete=applied,
            commit_created=False,
            merge_performed=False,
            push_performed=False,
            failure_reason=None if applied else failure_reason,
        )


def _gemini_args(prompt: str, model: str) -> tuple[str, ...]:
    return ("--skip-trust", "--approval-mode", "auto_edit", "-m", model, "-p", prompt, "--output-format", "json")


def _opencode_args(prompt: str, model: str) -> tuple[str, ...]:
    return ("run", "--auto", "--model", model, prompt)


def _mimo_args(prompt: str, model: str) -> tuple[str, ...]:
    return ("run", "--never-ask-questions", "--model", model, prompt)


class WorkerRegistry:
    def __init__(self, adapters: dict[str, WorkerAdapter]):
        adapters = dict(adapters)
        missing = set(SUPPORTED_WORKER_PROVIDERS) - set(adapters)
        if missing == {"agy"}:
            adapters["agy"] = AgyWorkerAdapter()
            missing = set()
        unknown = set(adapters) - set(SUPPORTED_WORKER_PROVIDERS)
        if unknown:
            raise ValueError(f"unknown worker providers: {sorted(unknown)}")
        if missing:
            raise ValueError(f"missing worker providers: {sorted(missing)}")
        self._adapters = dict(adapters)

    @classmethod
    def default(cls) -> "WorkerRegistry":
        return cls(
            {
                "codex": CodexWorkerAdapter(),
                "gemini": DirectCliWorkerAdapter("gemini", "gemini", "NEXUS_GEMINI_WORKER_MODEL", "gemini-2.5-flash", _gemini_args),
                "agy": AgyWorkerAdapter(),
                "opencode": DirectCliWorkerAdapter("opencode", "opencode", "NEXUS_OPENCODE_WORKER_MODEL", "opencode/big-pickle", _opencode_args),
                "mimo": DirectCliWorkerAdapter("mimo", "mimo", "NEXUS_MIMO_WORKER_MODEL", "mimo", _mimo_args),
                "ollama": OllamaPatchWorkerAdapter(),
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
