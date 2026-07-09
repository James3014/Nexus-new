from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class P8CP9ReadinessDecision:
    readiness_version: str = "1.0"
    decision: str = "P8_C_AUDIT_BLOCKED_WITH_REASONS"
    manifest_complete: bool = False
    receipt_structurally_valid: bool = False
    redaction_audit_passed: bool = False
    call_budget_audit_passed: bool = False
    authority_audit_passed: bool = False
    smoke_completed: bool = False
    network_call_count: int = 0
    rollback_required: bool = False
    p9_may_start: bool = False
    p9_requires_explicit_human_approval: bool = True
    p9_max_batch_size_recommendation: int = 5
    p9_no_apply_required: bool = True
    p9_no_public_claim_required: bool = True
    p9_no_production_required: bool = True
    blocked_reasons: list[str] = field(default_factory=list)


def evaluate_p9_readiness(
    *,
    manifest_complete: bool,
    receipt_structurally_valid: bool,
    redaction_audit_passed: bool,
    call_budget_audit_passed: bool,
    authority_audit_passed: bool,
    smoke_completed: bool,
    network_call_count: int = 0,
    rollback_required: bool = False,
) -> P8CP9ReadinessDecision:
    blocked = []
    rollback = []

    if not manifest_complete: blocked.append("manifest_incomplete")
    if not receipt_structurally_valid: blocked.append("receipt_invalid")
    if not redaction_audit_passed: blocked.append("redaction_failed")
    if not call_budget_audit_passed: blocked.append("call_budget_failed")
    if not authority_audit_passed: blocked.append("authority_failed")
    if not smoke_completed: blocked.append("smoke_not_completed")
    if network_call_count == 0 and smoke_completed: blocked.append("zero_calls_with_completed")
    if network_call_count > 1: rollback.append("network_call_count_exceeded")
    if rollback_required: rollback.append("audit_rollback_required")

    all_blocked = blocked + rollback
    p9_ready = len(all_blocked) == 0 and smoke_completed and network_call_count == 1

    if rollback:
        decision = "P8_C_AUDIT_ROLLBACK_REQUIRED"
    elif len(blocked) > 0:
        decision = "P8_C_AUDIT_BLOCKED_WITH_REASONS"
    elif p9_ready:
        decision = "P8_C_AUDIT_PASSED_P9_READY"
    else:
        decision = "P8_C_AUDIT_BLOCKED_WITH_REASONS"

    return P8CP9ReadinessDecision(
        decision=decision,
        manifest_complete=manifest_complete,
        receipt_structurally_valid=receipt_structurally_valid,
        redaction_audit_passed=redaction_audit_passed,
        call_budget_audit_passed=call_budget_audit_passed,
        authority_audit_passed=authority_audit_passed,
        smoke_completed=smoke_completed,
        network_call_count=network_call_count,
        rollback_required=rollback_required,
        p9_may_start=p9_ready,
        blocked_reasons=all_blocked,
    )
