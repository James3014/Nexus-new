"""Automatic isolated candidate commit and human promotion packet."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path

from nexus.orchestrator.candidate_verifier import VerifiedCandidateReceipt
from nexus.orchestrator.task_contract import SelfHostedTaskContract
from nexus.orchestrator.worktree_manager import TargetWorktreeLease, WorktreeManager


@dataclass(frozen=True)
class PromotionApprovalPacket:
    schema: str
    task_id: str
    contract_hash: str
    controller_revision: str
    target_base_revision: str
    candidate_state_hash: str
    candidate_commit_sha: str
    candidate_tree_sha: str
    verified_receipt_hash: str
    candidate_commit_created: bool
    promotion_status: str
    public_claim_allowed: bool
    production_ready: bool
    merge_performed: bool
    push_performed: bool


class CandidateCommitter:
    AUTHOR_NAME = "Nexus Candidate Bot"
    AUTHOR_EMAIL = "nexus-candidate@localhost"

    def __init__(self, worktree_manager: WorktreeManager):
        self.worktree_manager = worktree_manager

    @staticmethod
    def _receipt_hash(receipt: VerifiedCandidateReceipt) -> str:
        canonical = json.dumps(
            asdict(receipt),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def create_candidate_commit(
        self,
        contract: SelfHostedTaskContract,
        lease: TargetWorktreeLease,
        receipt: VerifiedCandidateReceipt,
    ) -> PromotionApprovalPacket:
        if not receipt.verified or not receipt.candidate_commit_allowed:
            raise RuntimeError("Verified Candidate Receipt is required before candidate commit")
        if receipt.candidate_commit_created or receipt.merge_performed:
            raise RuntimeError("receipt already contains a promotion mutation")

        target = Path(lease.target_worktree).resolve()
        current = self.worktree_manager.capture_candidate(contract, lease)
        if current.candidate_state_hash != receipt.candidate_state_hash:
            raise RuntimeError("candidate state changed after verification")
        staged_before = self.worktree_manager._run_git(
            ["diff", "--cached", "--name-only"],
            cwd=target,
        )
        if staged_before:
            raise RuntimeError("Target index must be clean before candidate commit")
        paths = sorted(set(current.changed_files) | set(current.untracked_files))
        if current.deleted_files:
            raise RuntimeError("candidate deletions must be rejected before commit")
        if not paths:
            raise RuntimeError("candidate commit requires a non-empty candidate diff")

        self.worktree_manager._run_git(["add", "--", *paths], cwd=target)
        staged_after = self.worktree_manager._run_git(
            ["diff", "--cached", "--name-only"],
            cwd=target,
        ).splitlines()
        if staged_after != paths:
            raise RuntimeError("staged candidate paths differ from verified paths")
        commit_env = os.environ.copy()
        commit_env["MUSE_RUN_CODEX_LOOP"] = "0"
        self.worktree_manager._run_git(
            [
                "-c",
                f"user.name={self.AUTHOR_NAME}",
                "-c",
                f"user.email={self.AUTHOR_EMAIL}",
                "commit",
                "-m",
                f"candidate({contract.task_id}): governed worker result",
            ],
            cwd=target,
            env=commit_env,
        )
        commit_sha = self.worktree_manager._run_git(["rev-parse", "HEAD"], cwd=target)
        tree_sha = self.worktree_manager._run_git(["rev-parse", "HEAD^{tree}"], cwd=target)
        committed_paths = self.worktree_manager._run_git(
            ["diff-tree", "--no-commit-id", "--name-only", "-r", commit_sha],
            cwd=target,
        ).splitlines()
        if committed_paths != paths:
            raise RuntimeError("candidate commit tree differs from verified paths")
        if self.worktree_manager._run_git(["status", "--short"], cwd=target):
            raise RuntimeError("candidate worktree is not clean after commit")
        self.worktree_manager.verify_controller_unchanged(contract)
        return PromotionApprovalPacket(
            schema="nexus.promotion_approval_packet.v1",
            task_id=contract.task_id,
            contract_hash=contract.contract_hash,
            controller_revision=contract.controller_revision,
            target_base_revision=contract.target_base_revision,
            candidate_state_hash=receipt.candidate_state_hash,
            candidate_commit_sha=commit_sha,
            candidate_tree_sha=tree_sha,
            verified_receipt_hash=self._receipt_hash(receipt),
            candidate_commit_created=True,
            promotion_status="PENDING_HUMAN_APPROVAL",
            public_claim_allowed=False,
            production_ready=False,
            merge_performed=False,
            push_performed=False,
        )
