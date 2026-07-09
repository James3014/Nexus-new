from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class P6CloseoutDecision:
    closeout_version: str = "1.0"
    decision: str = "P6_CLOSED_BLOCKED"
    g1_harness_passed: bool = False
    g2_receipt_artifact_present: bool = False
    g3_monitor_canary_passed: bool = False
    g4_handoff_trace_present: bool = False
    real_execution_evidence_present: bool = False
    runtime_behavior_changed: bool = False
    all_rows_dry_run_only: bool = True
    all_rows_verifier_required: bool = True
    all_rows_claim_gate_required: bool = True
    all_rows_public_claim_false: bool = True
    all_rows_production_ready_false: bool = True
    p6_overrode_p3_topology: bool = False
    p6_overrode_p4_verifier: bool = False
    p6_overrode_claim_gate: bool = False
    p6_marked_solved: bool = False
    p6_set_public_claim_allowed: bool = False
    final_public_claim_allowed: bool = False
    final_production_ready: bool = False
    blocked_reasons: list[str] = field(default_factory=list)


def evaluate_closeout(
    *,
    g1_harness_passed: bool,
    g2_receipt_artifact_present: bool,
    g3_monitor_canary_passed: bool,
    g4_handoff_trace_present: bool,
    g3_summary: dict[str, Any] | None = None,
) -> P6CloseoutDecision:
    """Evaluate final P6 closeout."""
    blocked = []
    has_real = False
    has_pub = False
    has_prod = False

    if g3_summary:
        has_real = g3_summary.get("real_execution_evidence_present", False)
        has_pub = g3_summary.get("public_claim_allowed", False)
        has_prod = g3_summary.get("production_ready", False)

    if not g1_harness_passed:
        blocked.append("g1_harness_failed")
    if not g2_receipt_artifact_present:
        blocked.append("g2_receipt_artifact_missing")
    if not g3_monitor_canary_passed:
        blocked.append("g3_monitor_canary_failed")
    if not g4_handoff_trace_present:
        blocked.append("g4_handoff_trace_missing")
    if has_real:
        blocked.append("real_execution_evidence_present")
    if has_pub:
        blocked.append("public_claim_allowed_detected")
    if has_prod:
        blocked.append("production_ready_detected")

    if has_real or has_pub or has_prod:
        decision = "P6_CLOSED_ROLLBACK_REQUIRED"
    elif len(blocked) > 0:
        decision = "P6_CLOSED_BLOCKED"
    elif g1_harness_passed and g2_receipt_artifact_present and g3_monitor_canary_passed and g4_handoff_trace_present:
        decision = "P6_CLOSED_HELDOUT_DRY_RUN_READY"
    else:
        decision = "P6_CLOSED_BLOCKED"

    return P6CloseoutDecision(
        decision=decision,
        g1_harness_passed=g1_harness_passed,
        g2_receipt_artifact_present=g2_receipt_artifact_present,
        g3_monitor_canary_passed=g3_monitor_canary_passed,
        g4_handoff_trace_present=g4_handoff_trace_present,
        real_execution_evidence_present=has_real,
        blocked_reasons=blocked,
    )
