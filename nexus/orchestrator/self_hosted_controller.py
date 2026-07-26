from typing import Optional

from nexus.executors.codex_executor import CodexCliExecutor
from nexus.orchestrator.task_contract import SelfHostedTaskContract
from nexus.orchestrator.worktree_manager import (
    CandidateDiffReceipt,
    TargetWorktreeLease,
    WorktreeManager,
)


class SelfHostedDevelopmentController:
    def __init__(
        self,
        worktree_manager: Optional[WorktreeManager] = None,
    ):
        self.worktree_manager = worktree_manager or WorktreeManager()

    def prepare_task(
        self,
        contract: SelfHostedTaskContract,
    ) -> TargetWorktreeLease:
        if not isinstance(contract, SelfHostedTaskContract):
            raise TypeError("contract must be a SelfHostedTaskContract")
        self.worktree_manager.verify_controller_unchanged(contract)
        return self.worktree_manager.create_lease(contract)

    def collect_candidate(
        self,
        contract: SelfHostedTaskContract,
        lease: TargetWorktreeLease,
    ) -> CandidateDiffReceipt:
        if not isinstance(contract, SelfHostedTaskContract):
            raise TypeError("contract must be a SelfHostedTaskContract")
        self.worktree_manager.validate_lease_identity(contract, lease)
        self.worktree_manager.verify_controller_unchanged(
            contract,
            expected_status_sha256=lease.controller_status_sha256,
        )
        return self.worktree_manager.capture_candidate(contract, lease)

    def execute_codex_candidate(
        self,
        contract: SelfHostedTaskContract,
        *,
        prompt: str,
        executor: Optional[CodexCliExecutor] = None,
    ) -> tuple[TargetWorktreeLease, object, CandidateDiffReceipt]:
        """Prepare Target, invoke one fresh Codex worker, then recover Git truth."""

        lease = self.prepare_task(contract)
        execution = (executor or CodexCliExecutor()).invoke(
            contract,
            lease,
            prompt=prompt,
        )
        if execution.provider != "codex":
            raise RuntimeError("self-hosted worker provider must be codex")
        if execution.commit_created or execution.merge_performed:
            raise RuntimeError("worker must not commit or merge")
        receipt = self.collect_candidate(contract, lease)
        return lease, execution, receipt
