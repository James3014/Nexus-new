"""Bounded Codex CLI adapter for the self-hosted Target vertical."""

from __future__ import annotations

import dataclasses
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from nexus.executors.cli_worker import (
    CliWorkerRequest,
    CliWorkerResult,
    CliWorkerStatus,
    run_cli_worker,
)
from nexus.executors.codex_run_boundary import (
    CODEX_RUN_HOME_UNAVAILABLE,
    codex_child_env,
    materialize_codex_home,
    target_integrity_failure,
    target_integrity_snapshot,
    write_back_refreshed_auth,
)
from nexus.orchestrator.task_contract import SelfHostedTaskContract
from nexus.orchestrator.worktree_manager import TargetWorktreeLease


@dataclass(frozen=True)
class CodexExecutionReceipt:
    provider: str
    task_id: str
    target_worktree: str
    worker_status: str
    exit_code: int | None
    executable_identity: str
    argv: tuple[str, ...]
    stdout_sha256: str
    stderr_sha256: str
    wall_time_ms: int
    process_group_id: int | None
    provider_calls: int
    commit_created: bool
    merge_performed: bool
    provider_attempt_count: int | None = None
    # Typed non-delivery reason when the run boundary failed (#2254); the exit
    # code is then forced non-zero so adapters that only read it fail the run.
    failure_reason: str | None = None


class CodexCliExecutor:
    DEFAULT_MODEL = "gpt-5.6-luna"
    DEFAULT_REASONING_EFFORT = "medium"
    VALID_REASONING_EFFORTS = frozenset({"low", "medium", "high", "xhigh"})

    def __init__(
        self,
        executable: str = "codex",
        timeout_seconds: float = 900.0,
        model: str | None = None,
        reasoning_effort: str | None = None,
        on_process_group: Optional[Callable[[Optional[int]], None]] = None,
    ):
        self.executable = executable
        self.timeout_seconds = timeout_seconds
        self.model = model if model is not None else (
            os.getenv("NEXUS_CODEX_WORKER_MODEL", "").strip() or self.DEFAULT_MODEL
        )
        configured_effort = reasoning_effort if reasoning_effort is not None else os.getenv(
            "NEXUS_CODEX_REASONING_EFFORT", ""
        ).strip()
        self.reasoning_effort = configured_effort or self.DEFAULT_REASONING_EFFORT
        if self.reasoning_effort not in self.VALID_REASONING_EFFORTS:
            raise ValueError("NEXUS_CODEX_REASONING_EFFORT must be one of low, medium, high, xhigh")
        self.on_process_group = on_process_group

    def _request(
        self,
        contract: SelfHostedTaskContract,
        lease: TargetWorktreeLease,
        prompt: str,
    ) -> CliWorkerRequest:
        if contract.task_id != lease.task_id:
            raise ValueError("contract and lease task_id mismatch")
        if contract.preferred_provider not in (None, "codex"):
            raise ValueError("Codex executor requires preferred_provider=codex")
        target = str(Path(lease.target_worktree).resolve())
        if not prompt.strip():
            raise ValueError("prompt must be non-empty")
        argv = (
            "exec",
            "--ephemeral",
            "-m",
            self.model,
            "-c",
            f"model_reasoning_effort={self.reasoning_effort}",
            "--json",
            "--sandbox",
            "workspace-write",
            "--cd",
            target,
            "--skip-git-repo-check",
            prompt,
        )
        return CliWorkerRequest(
            executable=self.executable,
            argv=argv,
            cwd=target,
            timeout_seconds=self.timeout_seconds,
        )

    @staticmethod
    def _receipt(
        contract: SelfHostedTaskContract,
        lease: TargetWorktreeLease,
        result: CliWorkerResult,
    ) -> CodexExecutionReceipt:
        started = result.status != CliWorkerStatus.START_FAILED
        invocation_count = int(started)
        return CodexExecutionReceipt(
            provider="codex",
            task_id=contract.task_id,
            target_worktree=str(Path(lease.target_worktree).resolve()),
            worker_status=result.status.value,
            exit_code=result.exit_code,
            executable_identity=result.executable_identity,
            argv=result.argv,
            stdout_sha256=result.stdout_sha256,
            stderr_sha256=result.stderr_sha256,
            wall_time_ms=result.wall_time_ms,
            process_group_id=result.process_group_id,
            provider_calls=invocation_count,
            provider_attempt_count=invocation_count,
            commit_created=False,
            merge_performed=False,
        )

    def invoke(
        self,
        contract: SelfHostedTaskContract,
        lease: TargetWorktreeLease,
        *,
        prompt: str,
        model: str | None = None,
    ) -> CodexExecutionReceipt:
        executor = self if model is None else CodexCliExecutor(
            executable=self.executable, timeout_seconds=self.timeout_seconds,
            model=model, reasoning_effort=self.reasoning_effort,
            on_process_group=self.on_process_group,
        )
        request = executor._request(contract, lease, prompt)
        target = Path(lease.target_worktree).resolve()
        # Disposable HOME carrying only the copied auth file and an allowlisted
        # environment (#2254): never the host HOME, ~/.ssh, ~/.config/gh or
        # the ambient tokens.  Removed after the run.
        run_home = Path(tempfile.mkdtemp(prefix="nexus-codex-home-"))
        try:
            refusal = materialize_codex_home(run_home)
            if refusal is not None:
                return self._boundary_failure(contract, lease, request, refusal)
            request = dataclasses.replace(
                request,
                env=codex_child_env(os.environ, home=run_home, tmpdir=run_home / "tmp"),
                exact_env=True,
                sweep_descendants_on_exit=True,
                sweep_roots=(str(target), str(run_home)),
            )
            before = target_integrity_snapshot(target)
            if self.on_process_group is None:
                result = run_cli_worker(request)
            else:
                result = run_cli_worker(request, on_process_group=self.on_process_group)
            receipt = self._receipt(contract, lease, result)
            failure = target_integrity_failure(before, target_integrity_snapshot(target))
            if failure is None and receipt.exit_code == 0:
                write_back_refreshed_auth(run_home)
            if failure is not None:
                receipt = dataclasses.replace(
                    receipt,
                    exit_code=receipt.exit_code if receipt.exit_code else 1,
                    failure_reason=failure,
                )
            return receipt
        finally:
            shutil.rmtree(run_home, ignore_errors=True)

    def _boundary_failure(
        self,
        contract: SelfHostedTaskContract,
        lease: TargetWorktreeLease,
        request: CliWorkerRequest,
        reason: str,
    ) -> CodexExecutionReceipt:
        return CodexExecutionReceipt(
            provider="codex",
            task_id=contract.task_id,
            target_worktree=str(Path(lease.target_worktree).resolve()),
            worker_status=CliWorkerStatus.START_FAILED.value,
            exit_code=1,
            executable_identity=request.executable,
            argv=request.argv,
            stdout_sha256=CliWorkerResult.hash_bytes(b""),
            stderr_sha256=CliWorkerResult.hash_bytes(b""),
            wall_time_ms=0,
            process_group_id=None,
            provider_calls=0,
            provider_attempt_count=0,
            commit_created=False,
            merge_performed=False,
            failure_reason=reason or CODEX_RUN_HOME_UNAVAILABLE,
        )
