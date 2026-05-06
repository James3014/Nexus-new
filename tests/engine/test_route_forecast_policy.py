from __future__ import annotations

from nexus.engine.capability_contracts import CapabilityPlan
from nexus.engine.route_forecast_policy import build_forecast_gate_shadow, build_pillar_signal_summary


def _plan(
    *,
    selected: list[str] | None = None,
    pending: list[str] | None = None,
    signal_snapshot: dict[str, object] | None = None,
) -> CapabilityPlan:
    return CapabilityPlan(
        schema_version="test",
        selected_capabilities=selected or [],
        required_capabilities=[],
        optional_capabilities=[],
        conditional_capabilities=[],
        pending_capabilities=pending or [],
        forbidden_capabilities=[],
        constraints=[],
        decision_trace=[],
        replan_trace=[],
        score=0.0,
        signal_snapshot=signal_snapshot or {},
    )


def test_forecast_policy_forces_l3_when_hazard_mapping_requires_it():
    shadow = build_forecast_gate_shadow(
        _plan(
            selected=["research"],
            signal_snapshot={"risk_score_0_100": 5, "confidence": 0.99, "hazard_forced_l3": True},
        )
    )

    assert shadow["schema"] == "nexus_forecast_gate_shadow_v1"
    assert shadow["shadow_mode"] is True
    assert shadow["suggested_tier"] == "L3_full_governed"
    assert shadow["suggested_tier_reason"] == "hazard_mapping_forced_l3"
    assert shadow["early_exit_candidate"] is False


def test_forecast_policy_marks_low_risk_memory_supported_route_as_early_exit_candidate():
    shadow = build_forecast_gate_shadow(
        _plan(
            selected=["baseline"],
            signal_snapshot={"risk_score_0_100": 5, "confidence": 0.97, "memory_hits": 2},
        )
    )

    assert shadow["suggested_tier"] == "L1_light_governed"
    assert shadow["suggested_tier_reason"] == "low_risk_light_route_candidate"
    assert shadow["early_exit_candidate"] is True
    assert shadow["early_exit_policy"] == "never_skip_mempalace_artifact_claim_delivery_gates"


def test_forecast_policy_does_not_early_exit_when_pending_capabilities_exist():
    shadow = build_forecast_gate_shadow(
        _plan(
            selected=["baseline"],
            pending=["claim_gate"],
            signal_snapshot={"risk_score_0_100": 5, "confidence": 0.97, "memory_hits": 2},
        )
    )

    assert shadow["suggested_tier"] == "L1_light_governed"
    assert shadow["early_exit_candidate"] is False


def test_pillar_summary_uses_selected_capabilities_and_signal_snapshot():
    summary = build_pillar_signal_summary(
        _plan(
            selected=["claim_gate", "mempalace_gate"],
            signal_snapshot={"confidence": 0.72, "lancedb_hits": 1, "findings_hits": 3},
        )
    )

    assert summary["LanceDB"]["active"] is True
    assert summary["Memory"]["active"] is True
    assert summary["MemPalace"]["active"] is True
    assert summary["Belief"]["active"] is True
    assert summary["Claim"]["active"] is True
    assert summary["Artifact"]["active"] is False
