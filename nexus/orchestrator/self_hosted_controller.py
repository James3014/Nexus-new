from typing import Optional

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
