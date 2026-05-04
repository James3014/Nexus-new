from __future__ import annotations

from nexus.engine.capability_planner import default_capability_nodes
from nexus.engine.capability_signals import build_capability_signals
from nexus.engine.route_signal_adapter import build_replan_trace, build_signal_snapshot


def test_build_replan_trace_emits_phase_reasons_and_active_capabilities():
    nodes = default_capability_nodes()
    states = {
        "research": "conditional",
        "artifact_gate": "required",
        "claim_gate": "required",
        "mempalace_gate": "required",
    }
    trace = build_replan_trace(
        states=states,
        phase_trace={"P": "planned"},
        risk_score=80,
        confidence=0.6,
        nodes=nodes,
    )

    phase_map = {item["phase"]: item for item in trace}
    assert "fill_context_gap" in phase_map["X"]["replan_reasons"]
    assert "recheck_governance_and_belief" in phase_map["D"]["replan_reasons"]
    assert "claim_and_artifact_fail_closed" in phase_map["A"]["replan_reasons"]
    assert phase_map["P"]["prior_state"] == "planned"


def test_build_signal_snapshot_includes_tier_and_policy_counts():
    signals = build_capability_signals(
        task_desc="Docs tidy",
        task_type="doc-fix",
        route={
            "route_features": {
                "risk_score": 15,
                "adjusted_root_cause_confidence": 0.9,
                "candidate_count": 1,
            },
            "autonomic_signals": {
                "policy_match_count": 6,
            },
        },
    )

    snapshot = build_signal_snapshot(
        signals=signals,
        routing_tier="L1_green_lane",
        routing_tier_reason="low_risk_low_ambiguity",
    )

    assert snapshot["routing_tier"] == "L1_green_lane"
    assert snapshot["routing_tier_reason"] == "low_risk_low_ambiguity"
    assert snapshot["policy_loaded_count"] == 6
    assert snapshot["policy_pruned_count"] == 4
    assert snapshot["global_policy_unpruned"] is True
