from __future__ import annotations

from nexus.engine.capability_contracts import CapabilityPlan
from nexus.engine.capability_executor_controls import build_executor_controls


def test_build_executor_controls_local_heal_enabled() -> None:
    plan = CapabilityPlan(
        schema_version="nexus_capability_plan_v1",
        selected_capabilities=["local_heal", "autoreason"],
        required_capabilities=["local_heal"],
        optional_capabilities=[],
        conditional_capabilities=[],
        pending_capabilities=[],
        forbidden_capabilities=[],
        constraints=[],
        decision_trace=[],
        replan_trace=[],
        score=100.0,
    )
    controls = build_executor_controls(plan)
    assert controls["enable_local_heal"] is True
    assert controls["local_heal_mode"] == "shadow_only"
    assert controls["local_heal_mutation_allowed"] is False
    assert controls["local_heal_receipt_required"] is True
    assert controls["hybrid_route_mode"] == "cloud_assisted_by_local_trace_only"
    assert controls["hybrid_route_authority"] == "trace_only"
    assert controls["hybrid_route_public_claim_allowed"] is False
    assert controls["hybrid_route_production_ready"] is False
    assert controls["enable_autoreason_executor"] is True


def test_build_executor_controls_local_heal_pending() -> None:
    plan = {
        "selected_capabilities": ["local_heal"],
        "pending_capabilities": ["local_heal"],
    }
    controls = build_executor_controls(plan)
    assert controls["enable_local_heal"] is False
    assert controls["local_heal_mode"] == "pending"
    assert "local_heal_mutation_allowed" not in controls


def test_build_executor_controls_local_heal_disabled() -> None:
    plan = {
        "selected_capabilities": ["autoreason"],
        "pending_capabilities": [],
    }
    controls = build_executor_controls(plan)
    assert controls["enable_local_heal"] is False
    assert controls["local_heal_mode"] == "disabled"
    assert "local_heal_mutation_allowed" not in controls
