from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from nexus.services.local_heal.quota_state import QuotaState, BudgetClass, resolve_quota_state
from nexus.services.local_heal.degradation_policy import evaluate_degradation_policy, DegradationDecision


@dataclass
class P6RuntimeHookResult:
    """P6-B4: Runtime hook result."""
    p6_enabled: bool
    degradation_action: str
    candidate_count_limit: int | None
    cloud_allowed: bool
    local_allowed: bool
    committee_allowed: bool
    p5_allowed: bool
    runtime_route_changed: bool
    decision: DegradationDecision | None = None


def evaluate_p6_runtime_hook(
    *,
    requested_candidate_count: int = 3,
    local_available: bool = True,
) -> P6RuntimeHookResult:
    """P6-B4: Evaluate P6 runtime hook with env guard.

    When NEXUS_ENABLE_P6_QUOTA_DEGRADATION=1:
    - P6 can affect candidate generation / committee routing
    - But never P4 verifier / claim gate

    When flag off:
    - Runtime behavior unchanged
    - p6_runtime_route_mutation_allowed=false
    """
    p6_enabled = os.environ.get("NEXUS_ENABLE_P6_QUOTA_DEGRADATION", "0") == "1"

    if not p6_enabled:
        return P6RuntimeHookResult(
            p6_enabled=False,
            degradation_action="keep_full_committee",
            candidate_count_limit=None,
            cloud_allowed=True,
            local_allowed=True,
            committee_allowed=True,
            p5_allowed=True,
            runtime_route_changed=False,
        )

    # P6 enabled — resolve quota state and evaluate policy
    quota_state = resolve_quota_state()
    decision = evaluate_degradation_policy(
        quota_state=quota_state,
        requested_candidate_count=requested_candidate_count,
        local_available=local_available,
    )

    return P6RuntimeHookResult(
        p6_enabled=True,
        degradation_action=decision.action,
        candidate_count_limit=decision.candidate_count_limit,
        cloud_allowed=decision.cloud_allowed,
        local_allowed=decision.local_allowed,
        committee_allowed=decision.committee_allowed,
        p5_allowed=decision.p5_allowed,
        runtime_route_changed=decision.action != "keep_full_committee",
        decision=decision,
    )


def apply_p6_runtime_hook(
    *,
    requested_candidate_count: int = 3,
    local_available: bool = True,
) -> P6RuntimeHookResult:
    """Apply P6 runtime hook. Returns result with degradation decision."""
    return evaluate_p6_runtime_hook(
        requested_candidate_count=requested_candidate_count,
        local_available=local_available,
    )
