from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class P6HeldoutE2ERow:
    row_version: str = "1.0"
    evidence_kind: str = "p6_heldout_dry_run_synthetic"
    real_execution_evidence: bool = False
    case_id: str = ""
    quota_scenario_budget_class: str = ""
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
    dry_run_only: bool = True
    blocked_reasons: list[str] = field(default_factory=list)


def generate_e2e_trace(dry_run_receipts: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Convert dry-run receipts to synthetic monitor rows and summarize."""
    rows = []
    for r in dry_run_receipts:
        row = P6HeldoutE2ERow(
            case_id=r.get("case_id", ""),
            quota_scenario_budget_class=r.get("quota_scenario", ""),
            degradation_action=r.get("degradation_action", ""),
            cloud_allowed=r.get("cloud_allowed", False),
            local_allowed=r.get("local_allowed", False),
            committee_allowed=r.get("committee_allowed", False),
            p5_allowed=r.get("p5_allowed", False),
            candidate_count_actual=r.get("candidate_count_min", 0),
            candidate_count_requested=r.get("candidate_count_max", 10),
            receipt_complete=r.get("receipt_complete", True),
            blocked_reasons=r.get("blocked_reasons", []),
        )
        real_ev = r.get("real_execution_evidence", False)
        pub_claim = r.get("public_claim_allowed", False)
        prod_ready = r.get("production_ready", False)
        rows.append({
            "evidence_kind": row.evidence_kind, "real_execution_evidence": real_ev,
            "case_id": row.case_id, "quota_scenario_budget_class": row.quota_scenario_budget_class,
            "runtime_decision_evaluated": row.runtime_decision_evaluated,
            "degradation_action": row.degradation_action, "cloud_allowed": row.cloud_allowed,
            "local_allowed": row.local_allowed, "committee_allowed": row.committee_allowed,
            "p5_allowed": row.p5_allowed, "candidate_count_actual": row.candidate_count_actual,
            "candidate_count_requested": row.candidate_count_requested,
            "unsafe_action_detected": row.unsafe_action_detected,
            "verifier_required": row.verifier_required, "claim_gate_required": row.claim_gate_required,
            "public_claim_allowed": pub_claim, "production_ready": prod_ready,
            "receipt_complete": row.receipt_complete, "dry_run_only": row.dry_run_only,
            "blocked_reasons": row.blocked_reasons,
        })

    has_real = any(r["real_execution_evidence"] for r in rows)
    has_pub = any(r["public_claim_allowed"] for r in rows)
    has_prod = any(r["production_ready"] for r in rows)

    severity = "info"
    canary_decision = "allow_rollout_candidate"
    triggers = []
    if has_real:
        severity = "rollback"
        canary_decision = "rollback_required"
        triggers.append("real_execution_evidence")
    if has_pub:
        severity = "rollback"
        canary_decision = "rollback_required"
        triggers.append("public_claim_allowed")
    if has_prod:
        severity = "rollback"
        canary_decision = "rollback_required"
        triggers.append("production_ready")

    summary = {
        "monitor_gate_passed": not has_real and not has_pub and not has_prod,
        "canary_decision": canary_decision,
        "canary_severity": severity,
        "rollback_triggers": triggers,
        "block_triggers": [],
        "pause_triggers": [],
        "total_rows": len(rows),
        "real_execution_evidence_present": has_real,
        "public_claim_allowed": has_pub,
        "production_ready": has_prod,
    }
    return rows, summary
