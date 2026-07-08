from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nexus.services.local_heal.quota_state import QuotaState, BudgetClass
from nexus.services.local_heal.degradation_policy import DegradationDecision


@dataclass(frozen=True)
class P6Receipt:
    """P6-B3: P6 receipt block for local_heal runtime receipt."""
    p6_enabled: bool = True
    p6_runtime_mode: str = "env_guarded"
    p6_quota_state_known: bool = False
    p6_budget_class: str = "unknown"
    p6_quota_source: str = "env"
    p6_quota_confidence: float = 0.0
    p6_degradation_action: str = "fail_closed"
    p6_degradation_reason: str = "quota_unknown_conservative"
    p6_candidate_count_limit: int | None = None
    p6_cloud_allowed: bool = False
    p6_local_allowed: bool = True
    p6_committee_allowed: bool = False
    p6_p5_allowed: bool = False
    p6_memory_signal_used_for_quota: bool = False
    p6_belief_signal_used_for_quota: bool = False
    p6_verifier_required: bool = True
    p6_claim_gate_required: bool = True
    p6_runtime_route_mutation_allowed: bool = False
    p6_env_guard_required: bool = True
    p6_public_claim_allowed: bool = False


def build_p6_receipt(
    *,
    quota_state: QuotaState,
    decision: DegradationDecision,
) -> P6Receipt:
    """Build P6 receipt from QuotaState and DegradationDecision."""
    return P6Receipt(
        p6_enabled=True,
        p6_runtime_mode="env_guarded",
        p6_quota_state_known=quota_state.quota_known,
        p6_budget_class=quota_state.budget_class.value,
        p6_quota_source=quota_state.source,
        p6_quota_confidence=quota_state.confidence,
        p6_degradation_action=decision.action,
        p6_degradation_reason=decision.reason,
        p6_candidate_count_limit=decision.candidate_count_limit,
        p6_cloud_allowed=decision.cloud_allowed,
        p6_local_allowed=decision.local_allowed,
        p6_committee_allowed=decision.committee_allowed,
        p6_p5_allowed=decision.p5_allowed,
        p6_memory_signal_used_for_quota=False,
        p6_belief_signal_used_for_quota=False,
        p6_verifier_required=True,
        p6_claim_gate_required=True,
        p6_runtime_route_mutation_allowed=False,
        p6_env_guard_required=True,
        p6_public_claim_allowed=False,
    )


def p6_receipt_to_dict(receipt: P6Receipt) -> dict[str, Any]:
    """Convert P6Receipt to serializable dict."""
    return {
        "p6_enabled": receipt.p6_enabled,
        "p6_runtime_mode": receipt.p6_runtime_mode,
        "p6_quota_state_known": receipt.p6_quota_state_known,
        "p6_budget_class": receipt.p6_budget_class,
        "p6_quota_source": receipt.p6_quota_source,
        "p6_quota_confidence": receipt.p6_quota_confidence,
        "p6_degradation_action": receipt.p6_degradation_action,
        "p6_degradation_reason": receipt.p6_degradation_reason,
        "p6_candidate_count_limit": receipt.p6_candidate_count_limit,
        "p6_cloud_allowed": receipt.p6_cloud_allowed,
        "p6_local_allowed": receipt.p6_local_allowed,
        "p6_committee_allowed": receipt.p6_committee_allowed,
        "p6_p5_allowed": receipt.p6_p5_allowed,
        "p6_memory_signal_used_for_quota": receipt.p6_memory_signal_used_for_quota,
        "p6_belief_signal_used_for_quota": receipt.p6_belief_signal_used_for_quota,
        "p6_verifier_required": receipt.p6_verifier_required,
        "p6_claim_gate_required": receipt.p6_claim_gate_required,
        "p6_runtime_route_mutation_allowed": receipt.p6_runtime_route_mutation_allowed,
        "p6_env_guard_required": receipt.p6_env_guard_required,
        "p6_public_claim_allowed": receipt.p6_public_claim_allowed,
    }
