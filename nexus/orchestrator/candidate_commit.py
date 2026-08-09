"""Automatic isolated candidate commit and human promotion packet."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
from typing import Optional

from nexus.orchestrator.candidate_verifier import VerifiedCandidateReceipt
from nexus.orchestrator.task_contract import SelfHostedTaskContract
from nexus.orchestrator.worktree_manager import TargetWorktreeLease, WorktreeManager, get_canonical_git_hooks_dir


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
    authority_change_required: bool = False
    authority_findings_sha256: str = ""
    collaboration_provenance: Optional[dict[str, object]] = None


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

    @staticmethod
    def _resolve_git_home() -> str:
        env_git_home = os.environ.get("NEXUS_GIT_HOME")
        if env_git_home is not None and env_git_home.strip() != "":
            raw_path = env_git_home.strip()
            path = Path(raw_path).resolve()
            if path.is_dir() and path.is_absolute():
                return str(path)
            raise RuntimeError(
                f"Explicit NEXUS_GIT_HOME is invalid or does not exist: '{raw_path}'"
            )

        try:
            import pwd

            uid = os.getuid()
            pw_dir = pwd.getpwuid(uid).pw_dir
            if pw_dir and pw_dir.strip() != "":
                path = Path(pw_dir.strip()).resolve()
                if path.is_dir() and path.is_absolute():
                    return str(path)
        except Exception:
            pass

        raise RuntimeError(
            "Failed to resolve safe Git HOME: NEXUS_GIT_HOME is unset/empty and POSIX OS-account home resolution failed"
        )

    def create_candidate_commit(
        self,
        contract: SelfHostedTaskContract,
        lease: TargetWorktreeLease,
        receipt: VerifiedCandidateReceipt,
    ) -> PromotionApprovalPacket:
        if not receipt.verified or not receipt.candidate_commit_allowed:
            raise RuntimeError("Verified Candidate Receipt is required before candidate commit")
        expected_authorized_deletions = tuple(sorted(set(contract.authorized_deletions)))
        expected_authorized_deletions_hash = hashlib.sha256(
            json.dumps(expected_authorized_deletions, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        receipt_authorized_deletions = tuple(sorted(set(receipt.authorized_deletions or ())))
        if receipt_authorized_deletions != expected_authorized_deletions:
            raise RuntimeError("verified receipt authorized deletions do not match contract")
        if receipt.authorized_deletions_hash != expected_authorized_deletions_hash and not (
            not expected_authorized_deletions and receipt.authorized_deletions_hash == ""
        ):
            raise RuntimeError("verified receipt authorized deletion hash does not match contract")
        if receipt.candidate_commit_created or receipt.merge_performed:
            raise RuntimeError("receipt already contains a promotion mutation")

        target = Path(lease.target_worktree).resolve()
        current = self.worktree_manager.capture_candidate(contract, lease)
        if current.candidate_state_hash != receipt.candidate_state_hash:
            raise RuntimeError("candidate state changed after verification")
        if (
            receipt.collaboration_gate_passed is not True
            or current.collaboration_provenance != receipt.collaboration_provenance
        ):
            raise RuntimeError("verified collaboration provenance is required")
        staged_before = self.worktree_manager._run_git(
            ["diff", "--cached", "--name-only"],
            cwd=target,
        )
        if staged_before:
            raise RuntimeError("Target index must be clean before candidate commit")
        paths = sorted(
            set(current.changed_files)
            | set(current.untracked_files)
            | set(current.deleted_files)
        )
        unauthorized_deletions = sorted(
            set(current.deleted_files) - set(contract.authorized_deletions)
        )
        if unauthorized_deletions:
            raise RuntimeError(
                "candidate contains undeclared deletions: " + ", ".join(unauthorized_deletions)
            )
        if not paths:
            raise RuntimeError("candidate commit requires a non-empty candidate diff")
        target_head = self.worktree_manager._run_git(["rev-parse", "HEAD"], cwd=target)
        if target_head != lease.initial_head:
            # Workers are allowed to create scoped commits in the isolated
            # Target.  Reuse that exact commit chain; never create a second
            # wrapper commit or rewrite worker history.
            if self.worktree_manager._run_git(["status", "--short"], cwd=target):
                raise RuntimeError("precommitted Target must be clean before capture")
            parents = self.worktree_manager._run_git(
                ["rev-list", "--parents", "-n", "1", target_head], cwd=target,
            ).split()
            if len(parents) != 2:
                raise RuntimeError("precommitted candidate must not be a merge commit")
            committed_paths = self.worktree_manager._run_git(
                ["diff", "--name-only", lease.initial_head, target_head], cwd=target,
            ).splitlines()
            if sorted(committed_paths) != paths:
                raise RuntimeError("committed candidate paths differ from verified paths")
            commit_sha = target_head
        else:
            self.worktree_manager._run_git(["add", "--", *paths], cwd=target)
            staged_after = self.worktree_manager._run_git(
                ["diff", "--cached", "--name-only"],
                cwd=target,
            ).splitlines()
            if staged_after != paths:
                raise RuntimeError("staged candidate paths differ from verified paths")
            commit_env = os.environ.copy()
            commit_env["GIT_CONFIG_NOSYSTEM"] = "1"
            commit_env["GIT_CONFIG_GLOBAL"] = "/dev/null"
            commit_env["MUSE_RUN_CODEX_LOOP"] = "0"
            commit_env["HOME"] = self._resolve_git_home()
            hooks_dir = get_canonical_git_hooks_dir(target)
            self.worktree_manager._run_git(
                [
                    "-c",
                    f"user.name={self.AUTHOR_NAME}",
                    "-c",
                    f"user.email={self.AUTHOR_EMAIL}",
                    "-c",
                    f"core.hooksPath={hooks_dir}",
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
            authority_change_required=receipt.authority_change_required,
            authority_findings_sha256=receipt.authority_findings_sha256,
            collaboration_provenance=current.collaboration_provenance,
        )
