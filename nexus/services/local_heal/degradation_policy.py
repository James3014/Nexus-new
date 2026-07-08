from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nexus.services.local_heal.quota_state import QuotaState, BudgetClass


@dataclass(frozen=True)
class DegradationDecision:
    """P6-B2: DegradationPolicy runtime decision contract."""
    action: str  # keep_full_committee | reduce_candidate_count | local_only | diagnosis_only | fail_closed
    reason: str
    quota_budget_class: str
    candidate_count_limit: int | None
    cloud_allowed: bool
    local_allowed: bool
    committee_allowed: bool
    p5_allowed: bool
    memory_signal_used_for_quota: bool
    verifier_required: bool
    claim_gate_required: bool
    runtime_route_mutation_allowed: bool
    env_guard_required: bool
    receipt_fields: dict[str, Any] = field(default_factory=dict)


def evaluate_degradation_policy(
    *,
    quota_state: QuotaState,
    requested_candidate_count: int = 3,
    local_available: bool = True,
) -> DegradationDecision:
    """P6-B2: Evaluate degradation policy from quota state.

    Rules:
    - healthy: keep_full_committee
    - constrained: reduce_candidate_count
    - exhausted + local: local_only
    - exhausted + no local: fail_closed
    - unknown: fail_closed (conservative)
    - memory/belief cannot change action
    - verifier_required = true, claim_gate_required = true
    - runtime_route_mutation_allowed = false
    """
    budget_class = quota_state.budget_class

    if budget_class == BudgetClass.HEALTHY:
        action = "keep_full_committee"
        reason = "quota_healthy"
        cloud_allowed = True
        local_allowed = True
        committee_allowed = True
        p5_allowed = True
        candidate_count_limit = None

    elif budget_class == BudgetClass.CONSTRAINED:
        action = "reduce_candidate_count"
        reason = "quota_constrained"
        cloud_allowed = True
        local_allowed = True
        committee_allowed = True
        p5_allowed = True
        candidate_count_limit = max(2, requested_candidate_count - 1)

    elif budget_class == BudgetClass.EXHAUSTED:
        if local_available:
            action = "local_only"
            reason = "quota_exhausted_local_available"
            cloud_allowed = False
            local_allowed = True
            committee_allowed = False
            p5_allowed = True
            candidate_count_limit = 1
        else:
            action = "fail_closed"
            reason = "quota_exhausted_local_unavailable"
            cloud_allowed = False
            local_allowed = False
            committee_allowed = False
            p5_allowed = False
            candidate_count_limit = 0

    else:  # UNKNOWN
        action = "fail_closed"
        reason = "quota_unknown_conservative"
        cloud_allowed = False
        local_allowed = local_available
        committee_allowed = False
        p5_allowed = False
        candidate_count_limit = 0

    receipt_fields = {
        "p6_quota_state_known": quota_state.quota_known,
        "p6_budget_class": budget_class.value,
        "p6_degradation_action": action,
        "p6_degradation_reason": reason,
        "p6_candidate_count_limit": candidate_count_limit,
        "p6_cloud_allowed": cloud_allowed,
        "p6_local_allowed": local_allowed,
        "p6_committee_allowed": committee_allowed,
        "p6_p5_allowed": p5_allowed,
        "p6_memory_signal_used_for_quota": False,
        "p6_runtime_route_mutation_allowed": False,
        "p6_env_guard_required": True,
    }

    return DegradationDecision(
        action=action,
        reason=reason,
        quota_budget_class=budget_class.value,
        candidate_count_limit=candidate_count_limit,
        cloud_allowed=cloud_allowed,
        local_allowed=local_allowed,
        committee_allowed=committee_allowed,
        p5_allowed=p5_allowed,
        memory_signal_used_for_quota=False,
        verifier_required=True,
        claim_gate_required=True,
        runtime_route_mutation_allowed=False,
        env_guard_required=True,
        receipt_fields=receipt_fields,
    )
