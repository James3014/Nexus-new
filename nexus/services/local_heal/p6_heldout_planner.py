from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class P6HeldoutPlanRow:
    plan_version: str = "1.0"
    case_id: str = ""
    task_difficulty: str = ""
    quota_scenario: str = ""
    planned_degradation_action: str = ""
    planned_cloud_allowed: bool = False
    planned_local_allowed: bool = False
    planned_committee_allowed: bool = False
    planned_p5_allowed: bool = False
    planned_candidate_count_min: int = 0
    planned_candidate_count_max: int = 0
    verifier_required: bool = True
    claim_gate_required: bool = True
    public_claim_allowed: bool = False
    production_ready: bool = False
    default_runtime_allowed: bool = False
    execution_allowed: bool = False
    dry_run_only: bool = True
    blocked_reasons: list[str] = field(default_factory=list)


def plan_heldout_row(row: dict[str, Any]) -> P6HeldoutPlanRow:
    """Convert fixture row to plan row. execution_allowed=false for all."""
    blocked = []

    action = row.get("expected_degradation_action", "")
    qs = row.get("quota_scenario", "")
    cmin = row.get("expected_candidate_count_min", 0)

    if qs == "unknown" and action == "keep_full_committee":
        blocked.append("unknown_quota_keep_full_committee")
    if qs == "constrained" and cmin < 2:
        blocked.append("constrained_candidate_count_below_2")

    return P6HeldoutPlanRow(
        case_id=row.get("case_id", ""),
        task_difficulty=row.get("task_difficulty", ""),
        quota_scenario=qs,
        planned_degradation_action=action,
        planned_cloud_allowed=row.get("expected_cloud_allowed", False),
        planned_local_allowed=row.get("expected_local_allowed", False),
        planned_committee_allowed=row.get("expected_committee_allowed", False),
        planned_p5_allowed=row.get("expected_p5_allowed", False),
        planned_candidate_count_min=row.get("expected_candidate_count_min", 0),
        planned_candidate_count_max=row.get("expected_candidate_count_max", 0),
        verifier_required=True,
        claim_gate_required=True,
        public_claim_allowed=False,
        production_ready=False,
        default_runtime_allowed=False,
        execution_allowed=False,
        dry_run_only=True,
        blocked_reasons=blocked,
    )
