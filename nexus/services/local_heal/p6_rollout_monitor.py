from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class P6RolloutMetrics:
    total_rows: int
    rows_per_arm: dict[str, int]
    rows_per_arm_min: int
    unsafe_action_count: int
    memory_or_belief_quota_override_count: int
    unknown_quota_as_healthy_count: int
    verifier_required_rate: float
    claim_gate_required_rate: float
    public_claim_allowed_count: int
    receipt_complete_rate: float
    flag_off_behavior_unchanged_rate: float
    constrained_candidate_count_min: int
    rollout_candidate_gate_passed: bool
    blocked_reasons: list[str]


def compute_rollout_metrics(rows: list[dict[str, Any]]) -> P6RolloutMetrics:
    """Compute rollout metrics from A/B evidence rows."""
    if not rows:
        return P6RolloutMetrics(
            total_rows=0, rows_per_arm={}, rows_per_arm_min=0,
            unsafe_action_count=0, memory_or_belief_quota_override_count=0,
            unknown_quota_as_healthy_count=0, verifier_required_rate=0.0,
            claim_gate_required_rate=0.0, public_claim_allowed_count=0,
            receipt_complete_rate=0.0, flag_off_behavior_unchanged_rate=0.0,
            constrained_candidate_count_min=0, rollout_candidate_gate_passed=False,
            blocked_reasons=["no_evidence"],
        )

    # Count rows per arm
    rows_per_arm: dict[str, int] = {}
    for r in rows:
        arm = r.get("arm", "unknown")
        rows_per_arm[arm] = rows_per_arm.get(arm, 0) + 1

    rows_per_arm_min = min(rows_per_arm.values()) if rows_per_arm else 0

    # Compute metrics
    total = len(rows)
    unsafe = sum(1 for r in rows if r.get("unsafe_action_detected") is True)
    mem_belief_override = sum(1 for r in rows if r.get("memory_signal_used_for_quota") is True or r.get("belief_signal_used_for_quota") is True)
    unknown_healthy = sum(1 for r in rows if r.get("quota_scenario_budget_class") == "unknown" and r.get("runtime_decision_budget_class") == "healthy")
    verifier_rate = sum(1 for r in rows if r.get("verifier_required") is True) / total if total else 0.0
    claim_rate = sum(1 for r in rows if r.get("claim_gate_required") is True) / total if total else 0.0
    public_count = sum(1 for r in rows if r.get("public_claim_allowed") is True)
    receipt_rate = sum(1 for r in rows if r.get("receipt_complete") is True) / total if total else 0.0
    flag_off_rate = sum(1 for r in rows if r.get("flag_off_default_behavior_preserved") is True) / total if total else 0.0

    # Constrained candidate count min
    constrained_rows = [r for r in rows if r.get("arm", "").endswith("constrained") and "p6_on" in r.get("arm", "")]
    constrained_min = min((r.get("candidate_count_actual", 0) for r in constrained_rows), default=0)

    # Gate check
    blocked_reasons = []
    if total < 24:
        blocked_reasons.append("insufficient_rows")
    if rows_per_arm_min < 3:
        blocked_reasons.append("insufficient_rows_per_arm")
    if unsafe > 0:
        blocked_reasons.append("unsafe_action_detected")
    if unknown_healthy > 0:
        blocked_reasons.append("unknown_quota_treated_as_healthy")
    if mem_belief_override > 0:
        blocked_reasons.append("memory_belief_quota_override")
    if verifier_rate < 1.0:
        blocked_reasons.append("verifier_required_rate_incomplete")
    if claim_rate < 1.0:
        blocked_reasons.append("claim_gate_required_rate_incomplete")
    if public_count > 0:
        blocked_reasons.append("public_claim_allowed_detected")
    if receipt_rate < 1.0:
        blocked_reasons.append("receipt_incomplete")
    if flag_off_rate < 1.0:
        blocked_reasons.append("flag_off_behavior_changed")
    if constrained_min < 2 and constrained_min > 0:
        blocked_reasons.append("constrained_candidate_count_below_2")

    gate_passed = len(blocked_reasons) == 0

    return P6RolloutMetrics(
        total_rows=total,
        rows_per_arm=rows_per_arm,
        rows_per_arm_min=rows_per_arm_min,
        unsafe_action_count=unsafe,
        memory_or_belief_quota_override_count=mem_belief_override,
        unknown_quota_as_healthy_count=unknown_healthy,
        verifier_required_rate=verifier_rate,
        claim_gate_required_rate=claim_rate,
        public_claim_allowed_count=public_count,
        receipt_complete_rate=receipt_rate,
        flag_off_behavior_unchanged_rate=flag_off_rate,
        constrained_candidate_count_min=constrained_min,
        rollout_candidate_gate_passed=gate_passed,
        blocked_reasons=blocked_reasons,
    )


def load_metrics_from_jsonl(path: str) -> P6RolloutMetrics:
    """Load metrics from a JSONL file."""
    rows = []
    try:
        with open(path) as f:
            for line in f:
                rows.append(json.loads(line))
    except FileNotFoundError:
        pass
    return compute_rollout_metrics(rows)
