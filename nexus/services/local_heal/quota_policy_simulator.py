from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class QuotaState:
    """Simulated quota state."""
    cloud_budget_remaining: float = 1.0
    local_budget_remaining: float = 1.0
    committee_budget_remaining: float = 1.0
    budget_class: str = "healthy"  # healthy | constrained | exhausted | unknown


@dataclass
class P6SimulationResult:
    """P6 simulator output."""
    quota_budget_class: str
    degradation_action: str  # keep_full_committee, reduce_candidate_count, local_only, diagnosis_only, skip_committee, fail_closed
    degradation_reason: str
    diagnostic_confidence: float
    audit_context: str
    policy_explanation: str
    memory_influenced: bool
    receipt_fragment: dict[str, Any] = field(default_factory=dict)


def simulate_p6_quota_policy(
    *,
    quota_state: QuotaState,
    memory_confidence_signal: float = 0.0,
    memory_decision_mode: str = "audit_only",
    p5_enabled: bool = False,
) -> P6SimulationResult:
    """P6 quota policy simulator — memory signals read-only.

    Memory does NOT affect quota budget class, P4 gates, or public_claim_allowed.
    Memory only affects: diagnostic confidence, audit context, policy explanation.
    """
    # 1. Read quota state
    budget_class = quota_state.budget_class

    # 2. Read memory signals (read-only — no influence on quota class)
    memory_influenced = memory_decision_mode == "decision_eligible"

    # 3. Read P5 status
    # P5 status doesn't affect quota decision

    # 4. Compute degradation recommendation
    if budget_class == "unknown":
        # Conservative: treat unknown as exhausted
        degradation_action = "fail_closed"
        degradation_reason = "quota_unknown_conservative"
    elif budget_class == "exhausted":
        degradation_action = "local_only"
        degradation_reason = "quota_exhausted"
    elif budget_class == "constrained":
        degradation_action = "reduce_candidate_count"
        degradation_reason = "quota_constrained"
    else:  # healthy
        degradation_action = "keep_full_committee"
        degradation_reason = "quota_healthy"

    # 5. Memory influence scope (ONLY diagnostic confidence, audit context, policy explanation)
    diagnostic_confidence = 0.5 + (memory_confidence_signal * 0.3 if memory_influenced else 0.0)
    audit_context = f"memory_decision_mode={memory_decision_mode}" if memory_influenced else "no_memory_context"
    policy_explanation = f"quota={budget_class}, memory_signal={memory_confidence_signal:.2f}"

    return P6SimulationResult(
        quota_budget_class=budget_class,
        degradation_action=degradation_action,
        degradation_reason=degradation_reason,
        diagnostic_confidence=diagnostic_confidence,
        audit_context=audit_context,
        policy_explanation=policy_explanation,
        memory_influenced=memory_influenced,
    )
