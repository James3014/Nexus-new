from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nexus.services.local_heal.p6_heldout_validator import validate_heldout_fixture
from nexus.services.local_heal.p6_heldout_planner import plan_heldout_row


@dataclass(frozen=True)
class P6HeldoutDryRunReceipt:
    receipt_version: str = "1.0"
    case_id: str = ""
    task_difficulty: str = ""
    quota_scenario: str = ""
    dry_run_only: bool = True
    execution_attempted: bool = False
    cloud_invoked: bool = False
    local_model_invoked: bool = False
    patch_apply_invoked: bool = False
    degradation_action: str = ""
    cloud_allowed: bool = False
    local_allowed: bool = False
    committee_allowed: bool = False
    p5_allowed: bool = False
    candidate_count_min: int = 0
    candidate_count_max: int = 0
    verifier_required: bool = True
    claim_gate_required: bool = True
    solved: bool = False
    claim_eligible: bool = False
    public_claim_allowed: bool = False
    production_ready: bool = False
    runtime_behavior_changed: bool = False
    receipt_complete: bool = True
    blocked_reasons: list[str] = field(default_factory=list)


def run_heldout_dry_run(fixture_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Load, validate, plan, and emit dry-run receipts. Never execute repairs."""
    validation = validate_heldout_fixture(fixture_rows)
    if not validation.valid:
        return {
            "total_rows": len(fixture_rows),
            "valid_rows": 0,
            "blocked_rows": len(fixture_rows),
            "receipts": [],
            "gate_passed": False,
            "blocked_reasons": validation.blocked_reasons,
        }

    receipts = []
    for row in fixture_rows:
        plan = plan_heldout_row(row)
        receipt = P6HeldoutDryRunReceipt(
            case_id=plan.case_id,
            task_difficulty=plan.task_difficulty,
            quota_scenario=plan.quota_scenario,
            degradation_action=plan.planned_degradation_action,
            cloud_allowed=plan.planned_cloud_allowed,
            local_allowed=plan.planned_local_allowed,
            committee_allowed=plan.planned_committee_allowed,
            p5_allowed=plan.planned_p5_allowed,
            candidate_count_min=plan.planned_candidate_count_min,
            candidate_count_max=plan.planned_candidate_count_max,
            receipt_complete=len(plan.blocked_reasons) == 0,
            blocked_reasons=plan.blocked_reasons,
        )
        receipts.append(receipt)

    blocked = [r for r in receipts if r.blocked_reasons]
    return {
        "total_rows": len(fixture_rows),
        "valid_rows": len(receipts) - len(blocked),
        "blocked_rows": len(blocked),
        "receipts": receipts,
        "gate_passed": len(blocked) == 0,
        "blocked_reasons": [],
    }
