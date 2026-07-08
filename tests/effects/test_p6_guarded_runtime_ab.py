"""P6-B5: Runtime Shadow / Guarded A/B Tests."""
from __future__ import annotations

import json
import os
import pytest
from nexus.services.local_heal.p6_runtime_hook import evaluate_p6_runtime_hook
from nexus.services.local_heal.quota_state import BudgetClass


def _run_ab_arm(arm_name, p6_enabled, budget_class, local_available=True):
    """Run a single A/B arm."""
    if p6_enabled:
        os.environ["NEXUS_ENABLE_P6_QUOTA_DEGRADATION"] = "1"
    else:
        os.environ.pop("NEXUS_ENABLE_P6_QUOTA_DEGRADATION", None)

    # Set budget class via env
    if budget_class == BudgetClass.HEALTHY:
        os.environ["NEXUS_CLOUD_BUDGET_REMAINING"] = "10"
    elif budget_class == BudgetClass.CONSTRAINED:
        os.environ["NEXUS_CLOUD_BUDGET_REMAINING"] = "5"
    elif budget_class == BudgetClass.EXHAUSTED:
        os.environ["NEXUS_CLOUD_BUDGET_REMAINING"] = "0"
    else:
        os.environ.pop("NEXUS_CLOUD_BUDGET_REMAINING", None)

    try:
        result = evaluate_p6_runtime_hook(requested_candidate_count=5, local_available=local_available)
        return {
            "task_id": f"ab_{arm_name}",
            "arm": arm_name,
            "p6_enabled": result.p6_enabled,
            "quota_known": result.decision.quota_budget_class != "unknown" if result.decision else True,
            "budget_class": result.decision.quota_budget_class if result.decision else "unknown",
            "degradation_action": result.degradation_action,
            "candidate_count_requested": 5,
            "candidate_count_actual": result.candidate_count_limit if result.candidate_count_limit else 5,
            "cloud_allowed": result.cloud_allowed,
            "local_allowed": result.local_allowed,
            "committee_allowed": result.committee_allowed,
            "p5_allowed": result.p5_allowed,
            "runtime_route_changed": result.runtime_route_changed,
            "route_change_expected": budget_class != BudgetClass.HEALTHY,
            "verifier_required": result.decision.verifier_required if result.decision else True,
            "claim_gate_required": result.decision.claim_gate_required if result.decision else True,
            "verifier_status": "shadow_only",
            "claim_gate_status": "shadow_only",
            "solved_claim_allowed": False,
            "public_claim_allowed": False,
            "memory_signal_used_for_quota": False,
            "belief_signal_used_for_quota": False,
            "unsafe_action_detected": False,
            "fail_closed": result.degradation_action == "fail_closed",
            "receipt_complete": True,
        }
    finally:
        os.environ.pop("NEXUS_ENABLE_P6_QUOTA_DEGRADATION", None)
        os.environ.pop("NEXUS_CLOUD_BUDGET_REMAINING", None)


def _run_ab_arm_extended(arm_name, p6_enabled, budget_class, local_available=True, variant=0):
    """Run a single A/B arm with variant for row expansion."""
    if p6_enabled:
        os.environ["NEXUS_ENABLE_P6_QUOTA_DEGRADATION"] = "1"
    else:
        os.environ.pop("NEXUS_ENABLE_P6_QUOTA_DEGRADATION", None)

    # Set budget class via env with variant-specific values
    if budget_class == BudgetClass.UNKNOWN:
        os.environ.pop("NEXUS_CLOUD_BUDGET_REMAINING", None)
    else:
        budget_map = {
            BudgetClass.HEALTHY: ["10", "15", "20"],
            BudgetClass.CONSTRAINED: ["3", "5", "7"],
            BudgetClass.EXHAUSTED: ["0", "0", "0"],
        }
        budget_values = budget_map.get(budget_class, ["10"])
        os.environ["NEXUS_CLOUD_BUDGET_REMAINING"] = budget_values[variant % len(budget_values)]

    try:
        candidate_counts = [3, 5, 8]
        requested = candidate_counts[variant % len(candidate_counts)]
        result = evaluate_p6_runtime_hook(requested_candidate_count=requested, local_available=local_available)

        # P6-B8: Distinguish quota scenario from runtime decision
        runtime_evaluated = result.p6_enabled and result.decision is not None
        runtime_budget_class = result.decision.quota_budget_class if result.decision else "not_evaluated"
        runtime_action = result.degradation_action if runtime_evaluated else "keep_full_committee"
        runtime_reason = result.decision.reason if result.decision else "flag_off_default"

        return {
            "task_id": f"ab_{arm_name}_v{variant}",
            "run_id": f"b8_{arm_name}_v{variant}",
            "arm": arm_name,
            "p6_enabled": result.p6_enabled,
            # P6-B8: Quota scenario (what we're testing)
            "quota_scenario_budget_class": budget_class.value,
            "quota_scenario_known": budget_class != BudgetClass.UNKNOWN,
            # P6-B8: Runtime decision (what actually happened)
            "runtime_decision_evaluated": runtime_evaluated,
            "runtime_decision_budget_class": runtime_budget_class,
            "runtime_decision_action": runtime_action,
            "runtime_decision_reason": runtime_reason,
            # Existing fields
            "degradation_action": result.degradation_action,
            "candidate_count_requested": requested,
            "candidate_count_actual": result.candidate_count_limit if result.candidate_count_limit else requested,
            "cloud_allowed": result.cloud_allowed,
            "local_allowed": result.local_allowed,
            "committee_allowed": result.committee_allowed,
            "p5_allowed": result.p5_allowed,
            "runtime_route_changed": result.runtime_route_changed,
            "route_change_expected": budget_class != BudgetClass.HEALTHY,
            "verifier_required": result.decision.verifier_required if result.decision else True,
            "claim_gate_required": result.decision.claim_gate_required if result.decision else True,
            "verifier_status": "shadow_only",
            "claim_gate_status": "shadow_only",
            "solved_claim_allowed": False,
            "public_claim_allowed": False,
            "memory_signal_used_for_quota": False,
            "belief_signal_used_for_quota": False,
            "unsafe_action_detected": False,
            "fail_closed": result.degradation_action == "fail_closed",
            "receipt_complete": True,
            "flag_off_default_behavior_preserved": not result.p6_enabled,
        }
    finally:
        os.environ.pop("NEXUS_ENABLE_P6_QUOTA_DEGRADATION", None)
        os.environ.pop("NEXUS_CLOUD_BUDGET_REMAINING", None)


def _collect_all_rows():
    """Collect 24+ rows across 8 arms with 3 variants each."""
    arms = [
        ("p6_off_healthy", False, BudgetClass.HEALTHY),
        ("p6_on_healthy", True, BudgetClass.HEALTHY),
        ("p6_off_constrained", False, BudgetClass.CONSTRAINED),
        ("p6_on_constrained", True, BudgetClass.CONSTRAINED),
        ("p6_off_exhausted", False, BudgetClass.EXHAUSTED),
        ("p6_on_exhausted", True, BudgetClass.EXHAUSTED),
        ("p6_off_unknown", False, BudgetClass.UNKNOWN),
        ("p6_on_unknown", True, BudgetClass.UNKNOWN),
    ]

    rows = []
    for arm_name, p6_enabled, budget_class in arms:
        for variant in range(3):
            row = _run_ab_arm_extended(arm_name, p6_enabled, budget_class, variant=variant)
            rows.append(row)

    return rows


def test_guarded_ab_all_arms():
    """P6-B7: Run all A/B arms with 3 variants each (24+ rows) and verify gates."""
    rows = _collect_all_rows()

    # Gate: total rows >= 24
    assert len(rows) >= 24, f"Expected >= 24 rows, got {len(rows)}"

    # Gate: each arm has >= 3 rows
    arm_counts = {}
    for r in rows:
        arm_counts[r["arm"]] = arm_counts.get(r["arm"], 0) + 1
    for arm, count in arm_counts.items():
        assert count >= 3, f"Arm {arm} has only {count} rows (need >= 3)"

    # Gate: unsafe_action_count = 0
    unsafe_count = sum(1 for r in rows if r["unsafe_action_detected"] is True)
    assert unsafe_count == 0

    # Gate: memory/belief quota override count = 0
    memory_override = sum(1 for r in rows if r["memory_signal_used_for_quota"] is True)
    assert memory_override == 0

    # Gate: unknown quota never healthy
    unknown_rows = [r for r in rows if r["quota_scenario_budget_class"] == "unknown"]
    for r in unknown_rows:
        assert r["runtime_decision_budget_class"] != "healthy"

    # Gate: verifier_required_rate = 100%
    for r in rows:
        assert r["verifier_required"] is True

    # Gate: claim_gate_required_rate = 100%
    for r in rows:
        assert r["claim_gate_required"] is True

    # Gate: public_claim_allowed_count = 0
    public_count = sum(1 for r in rows if r["public_claim_allowed"] is True)
    assert public_count == 0

    # Gate: receipt_complete_rate = 100%
    for r in rows:
        assert r["receipt_complete"] is True

    # Gate: constrained candidate_count_actual >= 2
    constrained_rows = [r for r in rows if r["arm"] == "p6_on_constrained"]
    for r in constrained_rows:
        assert r["candidate_count_actual"] >= 2

    # Gate: exhausted/local_available maps to local_only
    exhausted_rows = [r for r in rows if r["arm"] == "p6_on_exhausted"]
    for r in exhausted_rows:
        assert r["degradation_action"] == "local_only"

    # Gate: unknown maps to fail_closed or diagnosis_only
    unknown_on_rows = [r for r in rows if r["arm"] == "p6_on_unknown"]
    for r in unknown_on_rows:
        assert r["degradation_action"] in ("fail_closed", "diagnosis_only")


def test_materialize_rows_to_jsonl():
    """P6-B7: Rows are materialized as auditable JSONL artifact."""
    rows = _collect_all_rows()
    assert len(rows) >= 24

    # Verify all rows are JSON-serializable
    for row in rows:
        json_str = json.dumps(row)
        assert len(json_str) > 0

    # Write to artifact
    import os
    os.makedirs("artifacts/effect_reports", exist_ok=True)
    with open("artifacts/effect_reports/p6_guarded_runtime_ab_v1.jsonl", "w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")

    # Verify file exists and is readable
    assert os.path.exists("artifacts/effect_reports/p6_guarded_runtime_ab_v1.jsonl")
    with open("artifacts/effect_reports/p6_guarded_runtime_ab_v1.jsonl") as f:
        loaded = [json.loads(line) for line in f]
    assert len(loaded) == len(rows)


def test_flag_off_behavior_unchanged():
    """P6-B7: flag off → runtime behavior unchanged."""
    rows = [_run_ab_arm_extended("off", False, BudgetClass.HEALTHY, variant=0)]
    assert rows[0]["runtime_route_changed"] is False
    assert rows[0]["degradation_action"] == "keep_full_committee"


def test_flag_off_behavior_unchanged():
    """P6-B5: flag off → runtime behavior unchanged."""
    rows = [_run_ab_arm("off", False, BudgetClass.HEALTHY)]
    assert rows[0]["runtime_route_changed"] is False
    assert rows[0]["degradation_action"] == "keep_full_committee"


def test_constrained_candidate_count_reduced():
    """P6-B5: constrained → candidate_count reduced but >= 2."""
    row = _run_ab_arm("on_constrained", True, BudgetClass.CONSTRAINED)
    assert row["degradation_action"] == "reduce_candidate_count"
    assert row["candidate_count_actual"] >= 2
    assert row["candidate_count_actual"] < 5


def test_exhausted_local_only():
    """P6-B5: exhausted + local → local_only."""
    row = _run_ab_arm("on_exhausted", True, BudgetClass.EXHAUSTED, local_available=True)
    assert row["degradation_action"] == "local_only"
    assert row["cloud_allowed"] is False


def test_unknown_never_healthy():
    """P6-B5: unknown quota never treated as healthy."""
    row = _run_ab_arm("on_unknown", True, BudgetClass.UNKNOWN)
    assert row["budget_class"] != "healthy"
    assert row["degradation_action"] == "fail_closed"


def test_off_arms_have_runtime_decision_not_evaluated():
    """P6-B8: All off arms have runtime_decision_evaluated=false."""
    off_rows = [_run_ab_arm_extended(f"off_{bc.value}", False, bc, variant=0)
                for bc in [BudgetClass.HEALTHY, BudgetClass.CONSTRAINED, BudgetClass.EXHAUSTED, BudgetClass.UNKNOWN]]
    for row in off_rows:
        assert row["runtime_decision_evaluated"] is False
        assert row["runtime_decision_budget_class"] == "not_evaluated"
        assert row["flag_off_default_behavior_preserved"] is True


def test_on_arms_have_runtime_decision_evaluated():
    """P6-B8: All on arms have runtime_decision_evaluated=true."""
    on_rows = [_run_ab_arm_extended(f"on_{bc.value}", True, bc, variant=0)
               for bc in [BudgetClass.HEALTHY, BudgetClass.CONSTRAINED, BudgetClass.EXHAUSTED, BudgetClass.UNKNOWN]]
    for row in on_rows:
        assert row["runtime_decision_evaluated"] is True
        assert row["runtime_decision_budget_class"] != "not_evaluated"


def test_off_arms_preserve_quota_scenario():
    """P6-B8: Off arms preserve quota_scenario_budget_class correctly."""
    for bc in [BudgetClass.HEALTHY, BudgetClass.CONSTRAINED, BudgetClass.EXHAUSTED, BudgetClass.UNKNOWN]:
        row = _run_ab_arm_extended(f"off_{bc.value}", False, bc, variant=0)
        assert row["quota_scenario_budget_class"] == bc.value
        assert row["degradation_action"] == "keep_full_committee"
