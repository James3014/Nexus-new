"""Bounded Codex CLI adapter for the self-hosted Target vertical."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from nexus.executors.cli_worker import CliWorkerResult, CliWorkerRequest, run_cli_worker
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


class CodexCliExecutor:
    def __init__(
        self,
        executable: str = "codex",
        timeout_seconds: float = 900.0,
        model: str = "gpt-5.5",
    ):
        self.executable = executable
        self.timeout_seconds = timeout_seconds
        self.model = model

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
        )

    def invoke(
        self,
        contract: SelfHostedTaskContract,
        lease: TargetWorktreeLease,
        *,
        prompt: str,
    ) -> CodexExecutionReceipt:
        request = self._request(contract, lease, prompt)
        result = run_cli_worker(request)
        return self._receipt(contract, lease, result)
