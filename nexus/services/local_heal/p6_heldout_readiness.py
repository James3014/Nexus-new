from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class P6HeldoutReadinessDecision:
    readiness_version: str = "1.0"
    decision: str = "P6_HELDOUT_NOT_READY"
    fixture_valid: bool = False
    plan_artifact_present: bool = False
    synthetic_monitor_rows_present: bool = False
    real_execution_evidence_present: bool = False
    all_rows_dry_run_only: bool = True
    all_rows_public_claim_false: bool = True
    all_rows_production_ready_false: bool = True
    all_rows_default_runtime_false: bool = True
    all_rows_verifier_required: bool = True
    all_rows_claim_gate_required: bool = True
    unknown_quota_safe: bool = True
    constrained_candidate_count_safe: bool = True
    fail_closed_permissions_safe: bool = True
    runtime_behavior_changed: bool = False
    blocked_reasons: list[str] = field(default_factory=list)


def evaluate_heldout_readiness(
    *,
    fixture_valid: bool,
    plan_artifact_present: bool,
    monitor_rows: list[dict[str, Any]],
    real_execution_evidence: bool = False,
) -> P6HeldoutReadinessDecision:
    """Evaluate heldout dry-run readiness."""
    blocked = []

    if not fixture_valid:
        blocked.append("fixture_invalid")
    if not plan_artifact_present:
        blocked.append("plan_artifact_missing")
    if not monitor_rows:
        blocked.append("no_monitor_rows")
    if real_execution_evidence:
        blocked.append("real_execution_evidence_present")

    # Check all rows
    all_dry_run = all(r.get("dry_run_only", True) for r in monitor_rows) if monitor_rows else False
    all_public_false = all(not r.get("public_claim_allowed", True) for r in monitor_rows) if monitor_rows else False
    all_prod_false = all(not r.get("production_ready", True) for r in monitor_rows) if monitor_rows else False
    all_runtime_false = all(not r.get("default_runtime_allowed", True) for r in monitor_rows) if monitor_rows else False
    all_verifier = all(r.get("verifier_required", False) for r in monitor_rows) if monitor_rows else False
    all_claim = all(r.get("claim_gate_required", False) for r in monitor_rows) if monitor_rows else False

    if not all_dry_run:
        blocked.append("not_all_dry_run")
    if not all_public_false:
        blocked.append("public_claim_allowed_detected")
    if not all_prod_false:
        blocked.append("production_ready_detected")
    if not all_runtime_false:
        blocked.append("default_runtime_allowed_detected")
    if not all_verifier:
        blocked.append("verifier_not_required")
    if not all_claim:
        blocked.append("claim_gate_not_required")

    if "public_claim_allowed_detected" in blocked or "production_ready_detected" in blocked:
        decision = "P6_HELDOUT_ROLLBACK_REQUIRED"
    elif len(blocked) > 0:
        decision = "P6_HELDOUT_BLOCKED"
    elif fixture_valid and plan_artifact_present and monitor_rows:
        decision = "P6_HELDOUT_DRY_RUN_READY"
    else:
        decision = "P6_HELDOUT_NOT_READY"

    return P6HeldoutReadinessDecision(
        decision=decision,
        fixture_valid=fixture_valid,
        plan_artifact_present=plan_artifact_present,
        synthetic_monitor_rows_present=bool(monitor_rows),
        real_execution_evidence_present=real_execution_evidence,
        all_rows_dry_run_only=all_dry_run,
        all_rows_public_claim_false=all_public_false,
        all_rows_production_ready_false=all_prod_false,
        all_rows_default_runtime_false=all_runtime_false,
        all_rows_verifier_required=all_verifier,
        all_rows_claim_gate_required=all_claim,
        unknown_quota_safe=True,
        constrained_candidate_count_safe=True,
        fail_closed_permissions_safe=True,
        runtime_behavior_changed=False,
        blocked_reasons=blocked,
    )
