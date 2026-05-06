from __future__ import annotations

from nexus.engine.capability_planner import CapabilityPlanner
from nexus.engine.route_tactical_policy import build_tactical_stop_policy


def test_tactical_stop_policy_orders_and_marks_evidence_required_tools():
    plan = CapabilityPlanner().plan(
        task_desc="Refactor credential scrubber while preserving secret redaction.",
        task_type="public_refactor",
        route={
            "recommended_flow": "hyper_sprint",
            "route_features": {
                "risk_score": 85,
                "candidate_count": 3,
                "has_hard_signal": True,
                "adjusted_root_cause_confidence": 0.45,
            },
        },
    )

    policy = build_tactical_stop_policy(plan=plan, recommended_flow="hyper_sprint")

    assert policy["tactical_sequence"][0] == "hyper_sprint"
    assert policy["tactical_sequence"].index("research") < policy["tactical_sequence"].index("autoreason")
    assert policy["tactical_sequence"].index("belief") < policy["tactical_sequence"].index("ultra_review")
    assert any(
        item["capability"] == "autoreason" and item["evidence_required"]
        for item in policy["tactical_tool_map"]
    )
    assert any(
        item["capability"] == "research" and item["purpose"] == "gather_evidence"
        for item in policy["tactical_tool_map"]
    )
    assert any(
        item["capability"] == "pregate" and not item["evidence_required"]
        for item in policy["tactical_tool_map"]
    )
    assert any(
        item["capability"] == "plan_quality_gate" and not item["evidence_required"]
        for item in policy["tactical_tool_map"]
    )


def test_tactical_stop_policy_preserves_caller_budget_fields():
    plan = CapabilityPlanner().plan(
        task_desc="Fix typo in README",
        task_type="doc-fix",
        route={"recommended_flow": "baseline", "route_features": {"risk_score": 5, "candidate_count": 1}},
    )

    policy = build_tactical_stop_policy(
        plan=plan,
        recommended_flow="baseline",
        base_policy={"type": "budget", "threshold": 1, "budget_guard": "fail_closed"},
    )

    assert policy["type"] == "budget"
    assert policy["threshold"] == 1
    assert policy["budget_guard"] == "fail_closed"
    assert policy["tactical_sequence"][0] == "baseline"
