"""Thin composition seam for Target reuse, transactional staging, and cleanup.

The existing lifecycle service remains the authority for task state, candidate
creation, verification, and promotion.  This module only binds those outputs
and performs real Git checks for an explicitly supplied, task-owned canary.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from nexus.contracts.target_integration_lifecycle import (
    AcceptanceReceipt,
    CleanupDecision,
    ExternalAcceptanceReceipt,
    IntegrationAuthorization,
    IntegrationAuthorizationEnvelope,
    IntegrationExecutionReceipt,
    IntegrationPreview,
    TargetResolution,
    TargetResolutionDecision,
    TargetResolutionMode,
)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode()).hexdigest()


class TargetIntegrationLifecycle:
    """Stateless adapter; lifecycle snapshots and receipts stay caller-owned."""

    _REQUIRED_ACTIONS = (
        "ACCEPT_DISPOSITION",
        "INTEGRATION_STAGING",
        "APPLY_VERIFIED_INTEGRATION",
        "POST_INTEGRATION_VERIFY",
        "CLEANUP_OWNED_TARGET",
        "DELETE_OWNED_TASK_BRANCH_IF_ELIGIBLE",
    )

    @staticmethod
    def resolve_target(
        *,
        task_id: str,
        campaign_id: str,
        attempt_id: str,
        base_revision: str,
        existing_targets: Iterable[Mapping[str, Any]],
        requested_target_path: str | None = None,
    ) -> TargetResolutionDecision:
        """Resolve from existing lifecycle-owned records, never from path names."""
        all_targets = [dict(item) for item in existing_targets]
        matches = [
            item for item in all_targets
            if str(item.get("task_id") or item.get("owner_task_id") or "") == task_id
            and str(item.get("campaign_id") or campaign_id) == campaign_id
        ]
        if requested_target_path:
            path_collision = next(
                (item for item in all_targets if str(item.get("target_path") or "") == requested_target_path and item not in matches),
                None,
            )
            if path_collision is not None:
                return TargetResolution(
                    schema="nexus.target_resolution_decision.v1", task_id=task_id,
                    campaign_id=campaign_id, attempt_id=attempt_id,
                    mode=TargetResolutionMode.BLOCK,
                    target_id=str(path_collision.get("target_id") or "unowned"),
                    target_path=requested_target_path,
                    target_branch=str(path_collision.get("target_branch") or "") or None,
                    base_revision=base_revision,
                    owner_task_id=str(path_collision.get("owner_task_id") or "") or None,
                    reason="requested Target path is already owned by another lifecycle identity",
                )
        if len(matches) > 1:
            return TargetResolution(
                schema="nexus.target_resolution_decision.v1", task_id=task_id,
                campaign_id=campaign_id, attempt_id=attempt_id,
                mode=TargetResolutionMode.BLOCK, target_id=None, target_path=None,
                target_branch=None, base_revision=base_revision, owner_task_id=task_id,
                reason="serial task has more than one active Target",
            )
        if matches:
            item = matches[0]
            target_id = str(item.get("target_id") or "")
            target_path = str(item.get("target_path") or "")
            target_branch = str(item.get("target_branch") or "")
            owner = str(item.get("owner_task_id") or item.get("task_id") or "")
            blockers: list[str] = []
            if not target_id or not target_path or not target_branch:
                blockers.append("target identity is incomplete")
            if owner != task_id:
                blockers.append("Target is not owned by this task")
            if str(item.get("base_revision") or base_revision) != base_revision:
                blockers.append("Target base revision drift")
            if bool(item.get("dirty")) or bool(item.get("untracked")):
                blockers.append("Target has dirty or untracked changes")
            if str(item.get("classification") or "").upper() in {"REVIEWER", "CANONICAL", "UNOWNED"}:
                blockers.append("Target classification is not lifecycle-owned")
            if blockers:
                return TargetResolution(
                    schema="nexus.target_resolution_decision.v1", task_id=task_id,
                    campaign_id=campaign_id, attempt_id=attempt_id,
                    mode=TargetResolutionMode.BLOCK, target_id=target_id or None,
                    target_path=target_path or None, target_branch=target_branch or None,
                    base_revision=base_revision, owner_task_id=owner or None,
                    reason="; ".join(blockers),
                )
            return TargetResolution(
                schema="nexus.target_resolution_decision.v1", task_id=task_id,
                campaign_id=campaign_id, attempt_id=attempt_id,
                mode=TargetResolutionMode.REUSE_EXISTING_TARGET, target_id=target_id,
                target_path=target_path, target_branch=target_branch,
                base_revision=base_revision, owner_task_id=task_id,
                reason="same stable task reuses its lifecycle-owned Target",
                reused=True,
            )
        generated = "target-" + _hash({"campaign_id": campaign_id, "task_id": task_id})[:16]
        return TargetResolution(
            schema="nexus.target_resolution_decision.v1", task_id=task_id,
            campaign_id=campaign_id, attempt_id=attempt_id,
            mode=TargetResolutionMode.CREATE_ISOLATED_TARGET, target_id=generated,
            target_path=requested_target_path,
            target_branch=f"nexus/task/{task_id}", base_revision=base_revision,
            owner_task_id=task_id, reason="no lifecycle-owned Target exists", reused=False,
        )

    @staticmethod
    def accept_candidate(
        *, task_id: str, attempt_id: str, candidate_commit: str,
        external_receipt: Mapping[str, Any] | ExternalAcceptanceReceipt | None,
        implementer_output: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Separate worker output from the independent acceptance authority."""
        del implementer_output  # A worker cannot manufacture acceptance.
        if external_receipt is None:
            return {"disposition": "PENDING_EXTERNAL_ACCEPTANCE", "accepted": False, "task_id": task_id, "attempt_id": attempt_id}
        receipt = external_receipt if isinstance(external_receipt, ExternalAcceptanceReceipt) else ExternalAcceptanceReceipt(**dict(external_receipt))
        if receipt.task_id != task_id or receipt.attempt_id != attempt_id or receipt.candidate_commit != candidate_commit:
            raise ValueError("external acceptance receipt does not bind task, attempt, and candidate")
        return {
            "disposition": "ACCEPTED",
            "accepted": True,
            "task_id": task_id,
            "attempt_id": attempt_id,
            "acceptance_receipt": receipt.to_dict(),
            "acceptance_receipt_hash": receipt.receipt_hash,
        }

    @classmethod
    def build_preview(
        cls, *, task_id: str, target_id: str, candidate_commit: str,
        acceptance: ExternalAcceptanceReceipt | Mapping[str, Any],
        canonical_branch: str, expected_canonical_head: str,
        verification_commands: Sequence[str], cleanup_target_id: str,
        rollback: str,
    ) -> IntegrationPreview:
        receipt = acceptance if isinstance(acceptance, ExternalAcceptanceReceipt) else ExternalAcceptanceReceipt(**dict(acceptance))
        if not receipt.passed or receipt.task_id != task_id or receipt.candidate_commit != candidate_commit:
            raise ValueError("integration preview requires matching external acceptance")
        payload = {
            "task_id": task_id, "target_id": target_id, "candidate_commit": candidate_commit,
            "acceptance_receipt_hash": receipt.receipt_hash,
            "canonical_branch": canonical_branch, "expected_canonical_head": expected_canonical_head,
            "strategy": "EPHEMERAL_WORKTREE_MERGE_THEN_APPLY",
            "verification_commands": list(verification_commands),
            "cleanup_target_id": cleanup_target_id, "rollback": rollback,
        }
        return IntegrationPreview(
            schema="nexus.integration_preview.v1", **payload, plan_hash=_hash(payload),
        )

    @classmethod
    def authorize(
        cls, *, task_id: str, campaign_id: str, task_card_hash: str,
        candidate_commit: str, candidate_receipt_hash: str,
        acceptance_receipt_hash: str, canonical_root: str,
        canonical_branch: str, expected_canonical_head: str,
        canonical_dirty_baseline: str, preview: IntegrationPreview,
        cleanup_target_id: str, cleanup_target_path: str, durable_ref: str,
        rollback: str, issued_at: str, expires_at: str | None = None,
        action_set: Sequence[str] | None = None,
    ) -> IntegrationAuthorizationEnvelope:
        actions = tuple(action_set or cls._REQUIRED_ACTIONS)
        if tuple(actions) != cls._REQUIRED_ACTIONS:
            raise ValueError("one-confirmation action set is incomplete or reordered")
        if preview.candidate_commit != candidate_commit or preview.acceptance_receipt_hash != acceptance_receipt_hash:
            raise ValueError("authorization preview binding mismatch")
        return IntegrationAuthorization(
            schema="nexus.integration_authorization.v1", task_id=task_id,
            campaign_id=campaign_id, task_card_hash=task_card_hash,
            candidate_commit=candidate_commit, candidate_receipt_hash=candidate_receipt_hash,
            acceptance_receipt_hash=acceptance_receipt_hash, canonical_root=canonical_root,
            canonical_branch=canonical_branch, expected_canonical_head=expected_canonical_head,
            canonical_dirty_baseline=canonical_dirty_baseline,
            integration_plan_hash=preview.plan_hash, action_set=actions,
            cleanup_target_id=cleanup_target_id, cleanup_target_path=cleanup_target_path,
            durable_ref=durable_ref, rollback=rollback, issued_at=issued_at,
            expires_at=expires_at,
        )

    @staticmethod
    def cleanup_decision(
        *, task_id: str, target_id: str, target_owner: str | None,
        target_is_canonical: bool, reviewer_worktree: bool, dirty: bool,
        untracked: bool, active_process: bool, accepted: bool, integrated: bool,
        canonical_contains_result: bool, durable_ref_verified: bool,
        receipts_complete: bool, unique_unprotected_commits: bool,
    ) -> CleanupDecision:
        reasons: list[str] = []
        if target_owner != task_id: reasons.append("target is not owned by task")
        if target_is_canonical: reasons.append("canonical Target is protected")
        if reviewer_worktree: reasons.append("Reviewer worktree is protected")
        if dirty: reasons.append("Target has tracked changes")
        if untracked: reasons.append("Target has untracked files")
        if active_process: reasons.append("Target has an active process or lock")
        if not accepted: reasons.append("candidate is not independently accepted")
        if not integrated: reasons.append("candidate is not integrated")
        if not canonical_contains_result: reasons.append("canonical does not contain integration result")
        if not durable_ref_verified: reasons.append("durable candidate/integration ref is missing")
        if not receipts_complete: reasons.append("required receipts are incomplete")
        if unique_unprotected_commits: reasons.append("Target has unique unprotected commits")
        decision = "ELIGIBLE" if not reasons else "RETAIN"
        actions = ("REMOVE_REGISTERED_WORKTREE", "PRUNE_WORKTREE_REGISTRY") if decision == "ELIGIBLE" else ()
        return CleanupDecision(
            schema="nexus.target_cleanup_decision.v1", decision=decision,
            task_id=task_id, target_id=target_id, reasons=tuple(reasons), actions=actions,
        )

    @staticmethod
    def bind_receipt(state: Mapping[str, Any], *, receipt_name: str, receipt: Mapping[str, Any]) -> dict[str, Any]:
        """Return a lifecycle state update; the existing service persists it."""
        if not receipt_name or not isinstance(receipt, Mapping):
            raise ValueError("receipt name and mapping are required")
        updated = dict(state)
        updated[receipt_name] = dict(receipt)
        updated[f"{receipt_name}_hash"] = _hash(receipt)
        return updated

    @staticmethod
    def _git(args: Sequence[str], cwd: str | Path) -> str:
        env = os.environ.copy()
        env["GIT_CONFIG_NOSYSTEM"] = "1"
        env["GIT_CONFIG_GLOBAL"] = "/dev/null"
        result = subprocess.run(
            ["git", "-c", "core.hooksPath=/dev/null", *args], cwd=cwd,
            capture_output=True, text=True, env=env,
        )
        if result.returncode:
            raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
        return result.stdout.strip()

    @classmethod
    def git_status_hash(cls, root: str | Path) -> str:
        status = cls._git(["status", "--porcelain=v1", "--untracked-files=all"], root)
        return hashlib.sha256(status.encode()).hexdigest()

    @classmethod
    def transactional_integration(
        cls, *, task_id: str, canonical_root: str | Path,
        candidate_commit: str, expected_canonical_head: str,
        expected_status_hash: str, staging_root: str | Path,
        verifier_commands: Sequence[Sequence[str]] = (), apply: bool = False,
        cleanup: CleanupDecision | None = None,
    ) -> IntegrationExecutionReceipt:
        """Use a real temporary worktree; canonical is touched only after checks pass."""
        root = Path(canonical_root).resolve()
        stage = Path(staging_root).resolve()
        before_head = cls._git(["rev-parse", "HEAD"], root)
        before_status = cls.git_status_hash(root)
        if before_head != expected_canonical_head:
            raise RuntimeError("canonical head drift")
        if before_status != expected_status_hash:
            raise RuntimeError("canonical dirty state drift")
        cls._git(["rev-parse", f"{candidate_commit}^{{commit}}"], root)
        if stage.exists():
            raise RuntimeError("staging Target already exists")
        stage.parent.mkdir(parents=True, exist_ok=True)
        cls._git(["worktree", "add", "--detach", str(stage), expected_canonical_head], root)
        try:
            cls._git(["merge", "--no-ff", "--no-edit", candidate_commit], stage)
            staged_head = cls._git(["rev-parse", "HEAD"], stage)
            for command in verifier_commands:
                result = subprocess.run(list(command), cwd=stage, capture_output=True, text=True)
                if result.returncode:
                    raise RuntimeError(f"staging verifier failed: {' '.join(command)}")
            if apply:
                if cls._git(["rev-parse", "HEAD"], root) != expected_canonical_head or cls.git_status_hash(root) != expected_status_hash:
                    raise RuntimeError("canonical drift before apply")
                cls._git(["merge", "--no-ff", "--no-edit", candidate_commit], root)
            after_head = cls._git(["rev-parse", "HEAD"], root)
            after_status = cls.git_status_hash(root)
        except Exception:
            subprocess.run(["git", "merge", "--abort"], cwd=stage, capture_output=True, text=True)
            raise
        finally:
            if stage.exists():
                cls._git(["worktree", "remove", str(stage)], root)
                cls._git(["worktree", "prune"], root)
        return IntegrationExecutionReceipt(
            schema="nexus.transactional_integration_receipt.v1", task_id=task_id,
            candidate_commit=candidate_commit, staging_commit=staged_head,
            integration_commit=after_head if apply else None, staged=True, applied=apply,
            canonical_head_before=before_head, canonical_head_after=after_head,
            canonical_status_before=before_status, canonical_status_after=after_status,
            verifier_passed=True,
            cleanup=cleanup or CleanupDecision(
                schema="nexus.target_cleanup_decision.v1", decision="RETAIN",
                task_id=task_id, target_id="unbound", reasons=("cleanup not evaluated",),
            ),
        )

    @classmethod
    def cleanup_target(
        cls, *, decision: CleanupDecision, target_path: str | Path,
        canonical_root: str | Path, apply: bool = False,
        branch: str | None = None, delete_branch_authorized: bool = False,
    ) -> dict[str, Any]:
        if decision.decision != "ELIGIBLE":
            return {"decision": decision.decision, "performed": False, "reasons": list(decision.reasons)}
        target = Path(target_path).resolve()
        canonical = Path(canonical_root).resolve()
        if target == canonical:
            raise RuntimeError("cleanup cannot remove canonical Target")
        registered = cls._git(["worktree", "list", "--porcelain"], canonical)
        if str(target) not in registered:
            raise RuntimeError("cleanup Target is not a registered worktree")
        if apply:
            cls._git(["worktree", "remove", str(target)], canonical)
            cls._git(["worktree", "prune"], canonical)
            if delete_branch_authorized and branch:
                if branch in {"main", "master", "develop", "production"}:
                    raise RuntimeError("protected branch deletion is forbidden")
                cls._git(["branch", "-d", branch], canonical)
        return {
            "decision": "REMOVED" if apply else "ELIGIBLE",
            "performed": apply, "target_path": str(target),
            "branch_deleted": bool(apply and delete_branch_authorized and branch),
        }
