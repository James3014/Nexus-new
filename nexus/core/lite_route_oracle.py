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

    # 2. Check if lane is policy-defined as receipt-lite
    if lane_name and lane_name in GATE_ONLY_RECEIPT_LITE_LANES:
        return LiteRouteDecision(
            is_lite=True,
            reason="lane_policy_gate_only_receipt_lite",
            skipped_phases=["X", "D", "A"],
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

    return LiteRouteDecision(
        is_lite=False,
        reason="standard_heavy_route",
        skipped_phases=[],
    )
