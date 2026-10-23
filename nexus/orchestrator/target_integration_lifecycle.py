"""Thin composition seam for Target reuse, integration authorization, and cleanup.

The existing lifecycle service remains the authority for task state, candidate
creation, verification, and promotion.  This module only binds those outputs
and performs real Git checks for an explicitly supplied, task-owned canary.

The unused compatibility entry for transactional staging and apply (and its
receipt type) was removed in #2584 Phase-2 batch A
(``ARCHIVED_2026-10-24_phase2_batch_A.md``). Integration runs only through
``SelfHostedTaskService.integrate_approved`` ->
``ControlledIntegrationManager.integrate_authorized_task_state``.
"""

from __future__ import annotations

import hashlib
import json
import re
import shlex
from typing import Any, Iterable, Mapping, Sequence

from nexus.contracts.target_integration_lifecycle import (
    AcceptanceReceipt,
    CleanupDecision,
    ExternalAcceptanceReceipt,
    IntegrationAuthorization,
    IntegrationAuthorizationEnvelope,
    IntegrationPreview,
    TargetResolution,
    TargetResolutionDecision,
    TargetResolutionMode,
)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode()).hexdigest()


def _render_command(argv: Sequence[str]) -> str:
    """Render argv as the human-readable command string the contract carries.

    Tokens stay bare unless they hold a character the downstream lexer
    (``shlex`` posix, comments on, ``punctuation_chars=";&|<>"``) treats
    specially: whitespace, quotes, backslash, ``#`` or ``;&|<>``.  Commands that
    already worked render byte-identically; any other token is shell-quoted so
    the contract string lexes back to exactly the argv the sealed evidence
    recorded (#2307).  Parentheses are not punctuation characters and stay bare.
    """
    return " ".join(
        token if token and not re.search(r"[\s'\"\\#;&|<>]", token) else shlex.quote(token)
        for token in argv
    )


class TargetIntegrationLifecycle:
    """Stateless validation/delegation adapter; existing services own mutations."""

    _REQUIRED_ACTIONS = (
        "ACCEPT_DISPOSITION",
        "INTEGRATION_STAGING",
        "APPLY_VERIFIED_INTEGRATION",
        "POST_INTEGRATION_VERIFY",
        "CLEANUP_OWNED_TARGET",
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
                reason="SERIAL_TASK_MULTIPLE_ACTIVE_TARGETS",
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
        attempt_id: str = "", candidate_tree_sha: str = "0" * 40,
        candidate_state_hash: str = "0" * 64, reviewer_id: str = "",
        verifier_artifact_hash: str = "", require_clean: bool = True,
        post_apply_commands: Sequence[str] = (),
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
            attempt_id=attempt_id, candidate_tree_sha=candidate_tree_sha,
            candidate_state_hash=candidate_state_hash, reviewer_id=reviewer_id,
            verifier_artifact_hash=verifier_artifact_hash, require_clean=require_clean,
            strategy=preview.strategy,
            verification_commands_hash=_hash(list(preview.verification_commands)),
            post_apply_commands_hash=_hash(list(post_apply_commands)),
            cleanup_requested=True, approval_scope="ALLOW_ACTION_ONCE",
        )

    @staticmethod
    def consume_authorization(authorization: Mapping[str, Any], *, consumed_at: str) -> dict[str, Any]:
        if not consumed_at:
            raise ValueError("consumed_at is required")
        if authorization.get("consumed_at"):
            raise RuntimeError("APPROVAL_ALREADY_CONSUMED")
        consumed = dict(authorization)
        consumed["approval_scope"] = "ALLOW_ACTION_ONCE"
        consumed["consumed_at"] = consumed_at
        return consumed

    @staticmethod
    def bind_receipt(state: Mapping[str, Any], *, receipt_name: str, receipt: Mapping[str, Any]) -> dict[str, Any]:
        """Build a state update; durable writes still go through SelfHostedTaskService."""
        if not receipt_name or not isinstance(receipt, Mapping):
            raise ValueError("receipt name and mapping are required")
        updated = dict(state)
        updated[receipt_name] = dict(receipt)
        updated[f"{receipt_name}_hash"] = _hash(receipt)
        return updated

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

    @classmethod
    def delegate_integration(
        cls, lifecycle_service: Any, task_id: str, *, integration_branch: str,
        runtime_identity: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Delegate the only production integration action to SelfHostedTaskService."""
        return lifecycle_service.integrate_approved(
            task_id, integration_branch=integration_branch, runtime_identity=runtime_identity,
        )

    @classmethod
    def delegate_cleanup(
        cls, lifecycle_service: Any, task_id: str, *, dry_run: bool = True,
    ) -> dict[str, Any]:
        """Delegate cleanup decisions and mutation to SelfHostedTaskService."""
        return lifecycle_service.cleanup_tasks(task_id=task_id, dry_run=dry_run)

    @staticmethod
    def persist_receipt(
        lifecycle_service: Any, task_id: str, *, receipt_name: str,
        receipt: Mapping[str, Any], status: str = "INTEGRATING",
    ) -> dict[str, Any]:
        """Persist through the existing service state repository, not a new store."""
        if not receipt_name or not isinstance(receipt, Mapping):
            raise ValueError("receipt name and mapping are required")
        state = lifecycle_service._read_state(task_id)
        if state is None:
            raise KeyError(task_id)
        values = {receipt_name: dict(receipt), f"{receipt_name}_hash": _hash(receipt)}
        return lifecycle_service._checkpoint(task_id, status, values, attempt_id=state.get("attempt_id"))

    @staticmethod
    def reload_receipt(
        lifecycle_service: Any, task_id: str, *, receipt_name: str,
    ) -> dict[str, Any]:
        state = lifecycle_service._read_state(task_id)
        if state is None or not isinstance(state.get(receipt_name), Mapping):
            raise KeyError(f"receipt not persisted: {task_id}/{receipt_name}")
        return dict(state[receipt_name])

    @classmethod
    def cleanup_target(
        cls, *, decision: CleanupDecision, target_path: str | Path,
        canonical_root: str | Path, apply: bool = False,
        branch: str | None = None, delete_branch_authorized: bool = False,
        authorization: Mapping[str, Any] | IntegrationAuthorizationEnvelope | None = None,
        lifecycle_state: Mapping[str, Any] | None = None,
        lifecycle_service: Any | None = None,
    ) -> dict[str, Any]:
        if decision.decision != "ELIGIBLE":
            return {"decision": decision.decision, "performed": False, "reasons": list(decision.reasons)}
        if authorization is None or lifecycle_state is None or lifecycle_service is None:
            return {"decision": "RETAIN", "performed": False, "reasons": ["cleanup requires persisted lifecycle authority"]}
        auth = authorization if isinstance(authorization, IntegrationAuthorizationEnvelope) else IntegrationAuthorizationEnvelope(**dict(authorization))
        if "CLEANUP_OWNED_TARGET" not in auth.action_set or not auth.cleanup_requested:
            return {"decision": "RETAIN", "performed": False, "reasons": ["cleanup authorization is incomplete"]}
        if lifecycle_state.get("status") != "INTEGRATED" or not lifecycle_state.get("integration_receipt"):
            return {"decision": "RETAIN", "performed": False, "reasons": ["integration receipt is missing"]}
        return cls.delegate_cleanup(lifecycle_service, lifecycle_state.get("task_id") or auth.task_id, dry_run=not apply)
