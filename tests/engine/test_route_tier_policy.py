from __future__ import annotations

from nexus.engine.route_tier_policy import build_route_derivation_meta, resolve_route_tier


def test_route_tier_policy_preserves_planner_tier_over_forecast_shadow():
    resolved = resolve_route_tier(
        signal_snapshot={"routing_tier": "L3_swarm_deep", "routing_tier_reason": "hazard_mapping_forced_l3"},
        forecast_gate_shadow={
            "suggested_tier": "L1_light_governed",
            "suggested_tier_reason": "low_risk_light_route_candidate",
            "early_exit_candidate": True,
        },
    )

    assert resolved.routing_tier == "L3_swarm_deep"
    assert resolved.routing_tier_reason == "hazard_mapping_forced_l3"
    assert resolved.routing_tier_fallback_used is False
    assert resolved.early_exit_used is False


def test_route_tier_policy_falls_back_to_forecast_shadow_when_planner_tier_missing():
    resolved = resolve_route_tier(
        signal_snapshot={},
        forecast_gate_shadow={
            "suggested_tier": "L2_context_governed",
            "suggested_tier_reason": "medium_risk_or_context_needed",
            "early_exit_candidate": False,
        },
    )

    assert resolved.routing_tier == "L2_context_governed"
    assert resolved.routing_tier_reason == "medium_risk_or_context_needed"
    assert resolved.routing_tier_fallback_used is True
    assert resolved.early_exit_used is False


def test_route_tier_policy_allows_early_exit_only_on_green_lane():
    resolved = resolve_route_tier(
        signal_snapshot={"routing_tier": "L1_green_lane", "routing_tier_reason": "low_risk_low_ambiguity"},
        forecast_gate_shadow={"early_exit_candidate": True},
    )

    assert resolved.early_exit_used is True


def test_route_derivation_meta_records_flow_mismatch_and_policy_rules():
    meta = build_route_derivation_meta(
        signal_snapshot={"recommended_flow": "baseline"},
        recommended_flow="hyper_sprint",
        routing_tier_fallback_used=True,
    )

    assert meta["routing_tier_fallback_used"] is True
    assert meta["recommended_flow_mismatch"] is True
    assert meta["recommended_flow_param"] == "hyper_sprint"
    assert meta["recommended_flow_plan"] == "baseline"
    assert meta["acceleration_layers_rule"] == "selected_capabilities_intersection_ddtree"
    assert meta["governance_layers_rule"] == "selected_capabilities_intersection_ultra_mempalace_artifact_claim"
