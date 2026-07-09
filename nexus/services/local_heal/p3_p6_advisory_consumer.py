from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class P3P6AdvisoryConsumptionResult:
    """P3-O6: P6 advisory handoff consumer contract.

    Defines how P3 may consume P6 advisory handoff rows without granting P6
    any authority over P3/P4/P5.
    """
    consumer_version: str
    p6_handoff_present: bool
    p6_recommendation: str
    p3_may_record_p6_receipt_ref: bool
    p3_topology_override_allowed: bool
    p4_verifier_override_allowed: bool
    p4_claim_gate_override_allowed: bool
    p5_selection_override_allowed: bool
    candidate_budget_advisory: str
    cloud_disabled_advisory: str
    local_only_advisory: str
    fail_closed_advisory: str
    p3_runtime_behavior_changed: bool
    full_verifier_required: bool
    claim_gate_required: bool
    solved_allowed: bool
    claim_eligible_allowed: bool
    public_claim_allowed: bool
    production_ready: bool
    blocked_reasons: list[str] = field(default_factory=list)


def compute_p3_p6_advisory_consumption(
    p6_handoff: dict[str, Any] | None = None,
) -> P3P6AdvisoryConsumptionResult:
    """Compute P6 advisory consumption result.

    Pure advisory: no P6 override, no runtime mutation.
    """
    blocked_reasons = []

    if p6_handoff is None:
        return P3P6AdvisoryConsumptionResult(
            consumer_version="1.0",
            p6_handoff_present=False,
            p6_recommendation="none",
            p3_may_record_p6_receipt_ref=True,
            p3_topology_override_allowed=False,
            p4_verifier_override_allowed=False,
            p4_claim_gate_override_allowed=False,
            p5_selection_override_allowed=False,
            candidate_budget_advisory="",
            cloud_disabled_advisory="",
            local_only_advisory="",
            fail_closed_advisory="",
            p3_runtime_behavior_changed=False,
            full_verifier_required=True,
            claim_gate_required=True,
            solved_allowed=False,
            claim_eligible_allowed=False,
            public_claim_allowed=False,
            production_ready=False,
            blocked_reasons=[],
        )

    recommendation = str(p6_handoff.get("recommendation", "") or "")
    topology_override = bool(p6_handoff.get("topology_override", False))
    verifier_override = bool(p6_handoff.get("verifier_override", False))
    claim_gate_override = bool(p6_handoff.get("claim_gate_override", False))
    p5_override = bool(p6_handoff.get("p5_override", False))

    if topology_override:
        blocked_reasons.append("p6_topology_override_attempted")
    if verifier_override:
        blocked_reasons.append("p6_verifier_override_attempted")
    if claim_gate_override:
        blocked_reasons.append("p6_claim_gate_override_attempted")
    if p5_override:
        blocked_reasons.append("p6_p5_override_attempted")

    candidate_budget = str(p6_handoff.get("candidate_budget", "") or "")
    cloud_disabled = str(p6_handoff.get("cloud_disabled", "") or "")
    local_only = str(p6_handoff.get("local_only", "") or "")
    fail_closed = str(p6_handoff.get("fail_closed", "") or "")

    return P3P6AdvisoryConsumptionResult(
        consumer_version="1.0",
        p6_handoff_present=True,
        p6_recommendation=recommendation,
        p3_may_record_p6_receipt_ref=True,
        p3_topology_override_allowed=False,
        p4_verifier_override_allowed=False,
        p4_claim_gate_override_allowed=False,
        p5_selection_override_allowed=False,
        candidate_budget_advisory=candidate_budget,
        cloud_disabled_advisory=cloud_disabled,
        local_only_advisory=local_only,
        fail_closed_advisory=fail_closed,
        p3_runtime_behavior_changed=False,
        full_verifier_required=True,
        claim_gate_required=True,
        solved_allowed=False,
        claim_eligible_allowed=False,
        public_claim_allowed=False,
        production_ready=False,
        blocked_reasons=blocked_reasons,
    )


def p3_p6_advisory_to_dict(result: P3P6AdvisoryConsumptionResult) -> dict[str, Any]:
    """Convert P3P6AdvisoryConsumptionResult to JSON-serializable dict."""
    return {
        "p3_p6_consumer_version": result.consumer_version,
        "p3_p6_handoff_present": result.p6_handoff_present,
        "p3_p6_recommendation": result.p6_recommendation,
        "p3_p6_may_record_receipt_ref": result.p3_may_record_p6_receipt_ref,
        "p3_p6_topology_override_allowed": result.p3_topology_override_allowed,
        "p3_p6_verifier_override_allowed": result.p4_verifier_override_allowed,
        "p3_p6_claim_gate_override_allowed": result.p4_claim_gate_override_allowed,
        "p3_p6_p5_override_allowed": result.p5_selection_override_allowed,
        "p3_p6_candidate_budget_advisory": result.candidate_budget_advisory,
        "p3_p6_cloud_disabled_advisory": result.cloud_disabled_advisory,
        "p3_p6_local_only_advisory": result.local_only_advisory,
        "p3_p6_fail_closed_advisory": result.fail_closed_advisory,
        "p3_p6_runtime_behavior_changed": result.p3_runtime_behavior_changed,
        "p3_p6_full_verifier_required": result.full_verifier_required,
        "p3_p6_claim_gate_required": result.claim_gate_required,
        "p3_p6_solved_allowed": result.solved_allowed,
        "p3_p6_claim_eligible_allowed": result.claim_eligible_allowed,
        "p3_p6_public_claim_allowed": result.public_claim_allowed,
        "p3_p6_production_ready": result.production_ready,
        "p3_p6_blocked_reasons": result.blocked_reasons,
    }
