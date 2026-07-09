from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class P6HeldoutMonitorRow:
    row_version: str = "1.0"
    evidence_kind: str = "heldout_plan_synthetic"
    case_id: str = ""
    quota_scenario_budget_class: str = ""
    runtime_decision_budget_class: str = "not_evaluated"
    runtime_decision_evaluated: bool = False
    degradation_action: str = ""
    cloud_allowed: bool = False
    local_allowed: bool = False
    committee_allowed: bool = False
    p5_allowed: bool = False
    candidate_count_actual: int = 0
    candidate_count_requested: int = 0
    unsafe_action_detected: bool = False
    verifier_required: bool = True
    claim_gate_required: bool = True
    public_claim_allowed: bool = False
    production_ready: bool = False
    receipt_complete: bool = True
    real_execution_evidence: bool = False
    blocked_reasons: list[str] = field(default_factory=list)


def convert_plan_row_to_monitor_row(plan_row: dict[str, Any]) -> P6HeldoutMonitorRow:
    """Convert heldout plan row to synthetic monitor row."""
    blocked = []

    qs = plan_row.get("quota_scenario", "")
    action = plan_row.get("planned_degradation_action", "")

    if qs == "unknown" and plan_row.get("planned_cloud_allowed") is True:
        blocked.append("unknown_cloud_allowed")

    return P6HeldoutMonitorRow(
        case_id=plan_row.get("case_id", ""),
        quota_scenario_budget_class=qs,
        degradation_action=action,
        cloud_allowed=plan_row.get("planned_cloud_allowed", False),
        local_allowed=plan_row.get("planned_local_allowed", False),
        committee_allowed=plan_row.get("planned_committee_allowed", False),
        p5_allowed=plan_row.get("planned_p5_allowed", False),
        candidate_count_actual=plan_row.get("planned_candidate_count_min", 0),
        candidate_count_requested=plan_row.get("planned_candidate_count_max", 10),
        verifier_required=plan_row.get("verifier_required", True),
        claim_gate_required=plan_row.get("claim_gate_required", True),
        public_claim_allowed=False,
        production_ready=False,
        receipt_complete=True,
        real_execution_evidence=False,
        blocked_reasons=blocked,
    )
