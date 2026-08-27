"""Bounded Codex CLI adapter for the self-hosted Target vertical."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

from nexus.contracts.fast_start_admission import (
    FastStartAdmissionDeniedError,
    FastStartAdmissionResult,
)
from nexus.executors.cli_worker import CliWorkerRequest, CliWorkerResult, run_cli_worker
from nexus.orchestrator.fast_start_admission import admit_managed_codex_launch
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
    admission_receipt: Optional[FastStartAdmissionResult] = None


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
        fast_start_snapshot: Optional[Mapping[str, Any]] = None,
        registry_fetcher: Optional[Callable[[], Mapping[str, Any] | None]] = None,
        metadata_fetcher: Optional[Callable[..., Mapping[str, Any]]] = None,
    ):
        self.executable = executable
        self.timeout_seconds = timeout_seconds
        self.model = (
            model
            if model is not None
            else (os.getenv("NEXUS_CODEX_WORKER_MODEL", "").strip() or self.DEFAULT_MODEL)
        )
        configured_effort = (
            reasoning_effort
            if reasoning_effort is not None
            else os.getenv("NEXUS_CODEX_REASONING_EFFORT", "").strip()
        )
        self.reasoning_effort = configured_effort or self.DEFAULT_REASONING_EFFORT
        if self.reasoning_effort not in self.VALID_REASONING_EFFORTS:
            raise ValueError("NEXUS_CODEX_REASONING_EFFORT must be one of low, medium, high, xhigh")
        self.on_process_group = on_process_group
        # Caller snapshot/fetchers are compatibility-only and are not retained
        # as launch authority.
        _ = (fast_start_snapshot, registry_fetcher, metadata_fetcher)

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
        admission_receipt: Optional[FastStartAdmissionResult] = None,
    ) -> CodexExecutionReceipt:
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
            provider_calls=1,
            commit_created=False,
            merge_performed=False,
            admission_receipt=admission_receipt,
        )

    def invoke(
        self,
        contract: SelfHostedTaskContract,
        lease: TargetWorktreeLease,
        *,
        prompt: str,
        model: str | None = None,
        admission_receipt: Optional[FastStartAdmissionResult] = None,
        fast_start_snapshot: Optional[Mapping[str, Any]] = None,
        registry_fetcher: Optional[Callable[[], Mapping[str, Any] | None]] = None,
        metadata_fetcher: Optional[Callable[..., Mapping[str, Any]]] = None,
    ) -> CodexExecutionReceipt:
        # G14 production admission: caller receipt/snapshot/fetchers are not
        # launch authority. Canonical #549 + metadata providers decide.
        _ = (admission_receipt, fast_start_snapshot, registry_fetcher, metadata_fetcher)
        admission = admit_managed_codex_launch(
            structured_issue=getattr(contract, "github_issue_number", None),
            task_id=contract.task_id,
            prompt=prompt,
            current_main_sha=lease.initial_head,
        )

        if not admission.codex_launch_allowed:
            raise FastStartAdmissionDeniedError(admission)

        executor = (
            self
            if model is None
            else CodexCliExecutor(
                executable=self.executable,
                timeout_seconds=self.timeout_seconds,
                model=model,
                reasoning_effort=self.reasoning_effort,
                on_process_group=self.on_process_group,
            )
        )
        request = executor._request(contract, lease, prompt)
        if self.on_process_group is None:
            result = run_cli_worker(request)
        else:
            result = run_cli_worker(request, on_process_group=self.on_process_group)
        return self._receipt(contract, lease, result, admission_receipt=admission)
