from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EvolutionTier(str, Enum):
    L1_LOCAL = "L1_local"
    L2_GOVERNED = "L2_governed"
    L3_SWARM = "L3_swarm"
    L4_META = "L4_meta"


@dataclass(frozen=True)
class ForgettingDecision:
    allowed: bool
    tier: EvolutionTier
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class ShadowPromotionDecision:
    status: str
    production_write_allowed: bool
    reason_codes: tuple[str, ...] = field(default_factory=tuple)


def decide_forgetting(
    tier: EvolutionTier | str,
    *,
    evidence_refs: list[str] | tuple[str, ...] = (),
    explicit_approval: bool = False,
) -> ForgettingDecision:
    """Apply the evolution ontology: high-tier forgetting needs evidence and approval."""
    tier_value = EvolutionTier(tier)
    reasons: list[str] = []
    if tier_value in {EvolutionTier.L3_SWARM, EvolutionTier.L4_META}:
        if not evidence_refs:
            reasons.append("missing_forgetting_evidence")
        if not explicit_approval:
            reasons.append("missing_explicit_approval")
    return ForgettingDecision(allowed=not reasons, tier=tier_value, reason_codes=tuple(reasons))


def build_quiet_moment_event(
    *,
    reason: str,
    affected_nodes: list[str] | tuple[str, ...],
    resume_after_seconds: int,
) -> dict[str, Any]:
    """Produce a transport-safe pause event for swarm mutation boundaries."""
    return {
        "schema_version": "nexus_quiet_moment.v1",
        "event_type": "quiet_moment",
        "reason": reason,
        "affected_nodes": list(affected_nodes),
        "resume_after_seconds": max(0, int(resume_after_seconds)),
        "allowed_actions": ["observe", "report", "rollback"],
        "production_writes_allowed": False,
    }


def evaluate_shadow_promotion(
    shadow_rows: list[dict[str, Any]],
    *,
    minimum_rows: int = 3,
    pass_rate_threshold: float = 0.8,
    allow_production_writes: bool = False,
) -> ShadowPromotionDecision:
    """Keep shadow competitions non-mutating until evidence quality clears promotion gates."""
    reasons: list[str] = []
    if allow_production_writes:
        reasons.append("shadow_must_not_write_production")
    if len(shadow_rows) < minimum_rows:
        reasons.append("insufficient_shadow_rows")
    passed = sum(1 for row in shadow_rows if bool(row.get("passed")))
    pass_rate = passed / len(shadow_rows) if shadow_rows else 0.0
    if pass_rate < pass_rate_threshold:
        reasons.append("shadow_pass_rate_below_threshold")
    if any(not row.get("evidence_ref") for row in shadow_rows):
        reasons.append("shadow_row_missing_evidence_ref")
    if reasons:
        return ShadowPromotionDecision(
            status="shadow_only",
            production_write_allowed=False,
            reason_codes=tuple(sorted(set(reasons))),
        )
    return ShadowPromotionDecision(status="eligible", production_write_allowed=False, reason_codes=())
