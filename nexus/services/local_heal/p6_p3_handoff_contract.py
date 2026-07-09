from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class P6P3HandoffContract:
    handoff_version: str = "1.0"
    p6_readiness_state: str = "rollout_candidate"
    p6_can_provide_quota_state: bool = True
    p6_can_provide_candidate_budget: bool = True
    p6_can_recommend_cloud_disabled: bool = True
    p6_can_recommend_local_only: bool = True
    p6_can_require_fail_closed: bool = True
    p6_can_override_p3_topology: bool = False
    p6_can_override_p4_verifier: bool = False
    p6_can_override_claim_gate: bool = False
    p6_can_mark_solved: bool = False
    p6_can_set_public_claim_allowed: bool = False
    p6_requires_env_guard: bool = True
    p6_requires_receipt: bool = True
    p6_requires_monitor_gate: bool = True
    p6_requires_canary_gate: bool = True
    p3_must_record_p6_receipt_ref: bool = True
    p3_must_preserve_shadow_or_guard_authority: bool = True
    p3_must_preserve_p4_final_authority: bool = True
    public_claim_allowed: bool = False
    production_ready: bool = False
    reason: str = ""


def build_handoff_contract(state: str = "rollout_candidate") -> P6P3HandoffContract:
    """Build P6-P3 handoff contract."""
    return P6P3HandoffContract(
        p6_readiness_state=state,
        reason=f"P6 {state} handoff contract",
    )
