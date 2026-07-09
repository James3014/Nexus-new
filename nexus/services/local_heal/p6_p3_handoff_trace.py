from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class P6P3HandoffRow:
    handoff_version: str = "1.1"
    source_artifact: str = "p6_heldout_monitor_canary_trace_v0"
    case_id: str = ""
    quota_scenario: str = ""
    p6_recommendation: str = ""
    candidate_budget_recommendation: str = ""
    cloud_disabled_recommendation: bool = False
    local_only_recommendation: bool = False
    fail_closed_recommendation: bool = False
    p6_can_override_p3_topology: bool = False
    p6_can_override_p4_verifier: bool = False
    p6_can_override_claim_gate: bool = False
    p6_can_mark_solved: bool = False
    p6_can_set_public_claim_allowed: bool = False
    p3_must_record_p6_receipt_ref: bool = True
    p3_must_preserve_p4_final_authority: bool = True
    public_claim_allowed: bool = False
    production_ready: bool = False
    blocked_reasons: list[str] = field(default_factory=list)


def _row_to_dict(row: P6P3HandoffRow) -> dict[str, Any]:
    return {
        "handoff_version": row.handoff_version, "source_artifact": row.source_artifact,
        "case_id": row.case_id, "quota_scenario": row.quota_scenario,
        "p6_recommendation": row.p6_recommendation,
        "candidate_budget_recommendation": row.candidate_budget_recommendation,
        "cloud_disabled_recommendation": row.cloud_disabled_recommendation,
        "local_only_recommendation": row.local_only_recommendation,
        "fail_closed_recommendation": row.fail_closed_recommendation,
        "p6_can_override_p3_topology": row.p6_can_override_p3_topology,
        "p6_can_override_p4_verifier": row.p6_can_override_p4_verifier,
        "p6_can_override_claim_gate": row.p6_can_override_claim_gate,
        "p6_can_mark_solved": row.p6_can_mark_solved,
        "p6_can_set_public_claim_allowed": row.p6_can_set_public_claim_allowed,
        "p3_must_record_p6_receipt_ref": row.p3_must_record_p6_receipt_ref,
        "p3_must_preserve_p4_final_authority": row.p3_must_preserve_p4_final_authority,
        "public_claim_allowed": row.public_claim_allowed,
        "production_ready": row.production_ready,
        "blocked_reasons": row.blocked_reasons,
    }


def generate_handoff_trace(trace_rows: list[dict[str, Any]], canary_severity: str = "info") -> list[dict[str, Any]]:
    """Convert trace rows to handoff rows. On rollback, preserve context while forcing fail_closed."""
    results = []
    for r in trace_rows:
        original_blocked = list(r.get("blocked_reasons", []))
        row = P6P3HandoffRow(
            case_id=r.get("case_id", ""),
            quota_scenario=r.get("quota_scenario_budget_class", ""),
            source_artifact=r.get("source_artifact", "p6_heldout_monitor_canary_trace_v0"),
            p6_recommendation=r.get("degradation_action", ""),
            candidate_budget_recommendation=r.get("candidate_budget_recommendation", ""),
            cloud_disabled_recommendation=not r.get("cloud_allowed", True),
            local_only_recommendation=r.get("degradation_action") == "local_only",
            fail_closed_recommendation=r.get("degradation_action") == "fail_closed",
            blocked_reasons=original_blocked,
        )
        if canary_severity == "rollback":
            merged_blocked = original_blocked + ["canary_severity_rollback"]
            row = P6P3HandoffRow(
                handoff_version=row.handoff_version,
                source_artifact=row.source_artifact,
                case_id=row.case_id,
                quota_scenario=row.quota_scenario,
                p6_recommendation="fail_closed",
                candidate_budget_recommendation=row.candidate_budget_recommendation,
                cloud_disabled_recommendation=True,
                local_only_recommendation=False,
                fail_closed_recommendation=True,
                blocked_reasons=merged_blocked,
            )
        results.append(_row_to_dict(row))
    return results
