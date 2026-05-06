from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ResolvedRouteTier:
    routing_tier: str
    routing_tier_reason: str
    routing_tier_fallback_used: bool
    early_exit_used: bool


def resolve_route_tier(
    *,
    signal_snapshot: dict[str, Any],
    forecast_gate_shadow: dict[str, Any],
) -> ResolvedRouteTier:
    routing_tier = str(signal_snapshot.get("routing_tier", "") or "")
    routing_tier_reason = str(signal_snapshot.get("routing_tier_reason", "") or "")
    routing_tier_fallback_used = False
    if not routing_tier:
        routing_tier_fallback_used = True
        routing_tier = str(forecast_gate_shadow.get("suggested_tier", "L2_context_governed"))
        routing_tier_reason = str(forecast_gate_shadow.get("suggested_tier_reason", "forecast_gate_default"))
    early_exit_used = bool(forecast_gate_shadow.get("early_exit_candidate", False) and routing_tier == "L1_green_lane")
    return ResolvedRouteTier(
        routing_tier=routing_tier,
        routing_tier_reason=routing_tier_reason,
        routing_tier_fallback_used=routing_tier_fallback_used,
        early_exit_used=early_exit_used,
    )


def build_route_derivation_meta(
    *,
    signal_snapshot: dict[str, Any],
    recommended_flow: str,
    routing_tier_fallback_used: bool,
) -> dict[str, Any]:
    plan_recommended_flow = str(signal_snapshot.get("recommended_flow", "") or "")
    return {
        "routing_tier_fallback_used": routing_tier_fallback_used,
        "recommended_flow_mismatch": bool(plan_recommended_flow and plan_recommended_flow != recommended_flow),
        "recommended_flow_param": recommended_flow,
        "recommended_flow_plan": plan_recommended_flow,
        "acceleration_layers_rule": "selected_capabilities_intersection_ddtree",
        "governance_layers_rule": "selected_capabilities_intersection_ultra_mempalace_artifact_claim",
    }
