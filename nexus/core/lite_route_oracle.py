import os
from dataclasses import dataclass
from typing import List, Optional

from nexus.engine.learning_policy_loader import (
    GATE_ONLY_RECEIPT_LITE_LANES,
    ROUTE_ORACLE_RECEIPT_LITE_CAPABILITIES,
    DETERMINISTIC_ROUTE_ORACLE_RECEIPT_LITE_CAPABILITIES,
)


@dataclass(frozen=True)
class LiteRouteDecision:
    is_lite: bool
    reason: str
    skipped_phases: List[str]


def should_use_lite_route(
    risk_level: str,
    impact_complexity: float,
    belief_confidence: float,
    lane_name: Optional[str] = None,
    capability_name: Optional[str] = None,
    route_cost_controls: Optional[dict] = None,
) -> LiteRouteDecision:
    """🛡️ Pure function SSOT for LiteRoute classification decisions."""
    # Convert inputs to standard formats
    risk_upper = str(risk_level).upper()

    # 1. NEXUS_LIGHT_ROUTE_FORCE env var acts as a hard override
    if os.environ.get("NEXUS_LIGHT_ROUTE_FORCE") == "1":
        return LiteRouteDecision(
            is_lite=True,
            reason="env_override_light_route_force",
            skipped_phases=["X", "D", "A"],
        )

    # Resolve effective lane with optional controls override
    effective_lane = lane_name
    if route_cost_controls and "route_lane" in route_cost_controls:
        effective_lane = route_cost_controls["route_lane"]

    # 2. Check if lane is policy-defined as receipt-lite (with context_sync_capped support)
    if effective_lane and (effective_lane in GATE_ONLY_RECEIPT_LITE_LANES or effective_lane == "context_sync_capped"):
        skipped = ["X", "A"] if effective_lane == "context_sync_capped" else ["X", "D", "A"]
        return LiteRouteDecision(
            is_lite=True,
            reason="lane_policy_gate_only_receipt_lite",
            skipped_phases=skipped,
        )

    # 3. Check if capability is policy-defined as receipt-lite
    if capability_name and (
        capability_name in ROUTE_ORACLE_RECEIPT_LITE_CAPABILITIES
        or capability_name in DETERMINISTIC_ROUTE_ORACLE_RECEIPT_LITE_CAPABILITIES
    ):
        return LiteRouteDecision(
            is_lite=True,
            reason="capability_policy_receipt_lite",
            skipped_phases=["X", "D", "A"],
        )

    # 4. Check environment variable override (respects risk/complexity constraints)
    if (
        os.environ.get("NEXUS_LIGHT_ROUTE") == "1"
        and risk_upper not in ("HIGH", "CRITICAL")
        and impact_complexity <= 3.0
    ):
        return LiteRouteDecision(
            is_lite=True,
            reason="env_override_light_route",
            skipped_phases=["X", "D", "A"],
        )

    # 5. Autonomic lite routing for low-risk, low-complexity tasks
    if risk_upper == "LOW" and impact_complexity <= 3.0:
        return LiteRouteDecision(
            is_lite=True,
            reason="auto_lite_low_risk_low_complexity",
            skipped_phases=["X", "D", "A"],
        )

    # 5b. Autonomic lite routing for normal-risk, low-complexity tasks with high belief confidence (excl. default 1.0)
    if risk_upper == "NORMAL" and impact_complexity <= 3.0 and 0.85 <= belief_confidence < 1.0:
        return LiteRouteDecision(
            is_lite=True,
            reason="auto_lite_normal_risk_high_confidence",
            skipped_phases=["X", "D", "A"],
        )

    return LiteRouteDecision(
        is_lite=False,
        reason="standard_heavy_route",
        skipped_phases=[],
    )
