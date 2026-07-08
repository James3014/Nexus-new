from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class P6RolloutReceipt:
    """P6-C2: Rollout candidate receipt v2."""
    p6_rollout_receipt_version: str = "2.0"
    p6_rollout_state: str = "env_guarded"
    p6_policy_version: str = "1.0"
    p6_env_guard_required: bool = True
    p6_default_runtime_allowed: bool = False
    p6_runtime_route_mutation_allowed: bool = False
    p6_public_claim_allowed: bool = False
    p6_production_ready: bool = False
    p6_verifier_required: bool = True
    p6_claim_gate_required: bool = True
    p6_memory_signal_allowed_for_quota: bool = False
    p6_belief_signal_allowed_for_quota: bool = False
    p6_p5_override_allowed: bool = False
    p6_evidence_total_rows: int = 0
    p6_evidence_rows_per_arm_min: int = 0
    p6_unsafe_action_count: int = 0
    p6_unknown_quota_as_healthy_count: int = 0
    p6_memory_or_belief_quota_override_count: int = 0
    p6_receipt_complete_rate: float = 0.0
    p6_flag_off_behavior_unchanged: bool = False
    p6_decision_reason: str = ""


def build_p6_rollout_receipt(
    *,
    rollout_state: str,
    total_rows: int,
    rows_per_arm_min: int,
    unsafe_action_count: int,
    unknown_quota_as_healthy_count: int,
    memory_or_belief_quota_override_count: int,
    receipt_complete_rate: float,
    flag_off_behavior_unchanged: bool,
    reason: str = "",
) -> P6RolloutReceipt:
    """Build P6 rollout receipt v2."""
    return P6RolloutReceipt(
        p6_rollout_state=rollout_state,
        p6_evidence_total_rows=total_rows,
        p6_evidence_rows_per_arm_min=rows_per_arm_min,
        p6_unsafe_action_count=unsafe_action_count,
        p6_unknown_quota_as_healthy_count=unknown_quota_as_healthy_count,
        p6_memory_or_belief_quota_override_count=memory_or_belief_quota_override_count,
        p6_receipt_complete_rate=receipt_complete_rate,
        p6_flag_off_behavior_unchanged=flag_off_behavior_unchanged,
        p6_decision_reason=reason,
    )


def p6_rollout_receipt_to_dict(receipt: P6RolloutReceipt) -> dict[str, Any]:
    """Convert P6RolloutReceipt to serializable dict."""
    return {
        "p6_rollout_receipt_version": receipt.p6_rollout_receipt_version,
        "p6_rollout_state": receipt.p6_rollout_state,
        "p6_policy_version": receipt.p6_policy_version,
        "p6_env_guard_required": receipt.p6_env_guard_required,
        "p6_default_runtime_allowed": receipt.p6_default_runtime_allowed,
        "p6_runtime_route_mutation_allowed": receipt.p6_runtime_route_mutation_allowed,
        "p6_public_claim_allowed": receipt.p6_public_claim_allowed,
        "p6_production_ready": receipt.p6_production_ready,
        "p6_verifier_required": receipt.p6_verifier_required,
        "p6_claim_gate_required": receipt.p6_claim_gate_required,
        "p6_memory_signal_allowed_for_quota": receipt.p6_memory_signal_allowed_for_quota,
        "p6_belief_signal_allowed_for_quota": receipt.p6_belief_signal_allowed_for_quota,
        "p6_p5_override_allowed": receipt.p6_p5_override_allowed,
        "p6_evidence_total_rows": receipt.p6_evidence_total_rows,
        "p6_evidence_rows_per_arm_min": receipt.p6_evidence_rows_per_arm_min,
        "p6_unsafe_action_count": receipt.p6_unsafe_action_count,
        "p6_unknown_quota_as_healthy_count": receipt.p6_unknown_quota_as_healthy_count,
        "p6_memory_or_belief_quota_override_count": receipt.p6_memory_or_belief_quota_override_count,
        "p6_receipt_complete_rate": receipt.p6_receipt_complete_rate,
        "p6_flag_off_behavior_unchanged": receipt.p6_flag_off_behavior_unchanged,
        "p6_decision_reason": receipt.p6_decision_reason,
    }
