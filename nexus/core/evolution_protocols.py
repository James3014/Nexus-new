from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
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


@dataclass(frozen=True)
class L3HardBlockWarning:
    allowed: bool
    tier: EvolutionTier
    reason_codes: tuple[str, ...]
    voice_warning_required: bool
    mtls_binding_required: bool
    warning_message: str


@dataclass(frozen=True)
class ShadowIsolationDecision:
    isolated: bool
    production_write_allowed: bool
    reason_codes: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class EvolutionMutationDecision:
    allowed: bool
    tier: EvolutionTier
    forgetting: ForgettingDecision
    warning: L3HardBlockWarning
    reason_codes: tuple[str, ...]


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


def build_l3_hard_block_warning(
    tier: EvolutionTier | str,
    *,
    reason_codes: list[str] | tuple[str, ...] = (),
    mtls_enabled: bool = False,
) -> L3HardBlockWarning:
    """Build the operator-facing hard stop for soul-tier mutations."""
    tier_value = EvolutionTier(tier)
    reasons = list(reason_codes)
    high_tier = tier_value in {EvolutionTier.L3_SWARM, EvolutionTier.L4_META}
    if high_tier and not mtls_enabled:
        reasons.append("missing_mtls_binding")
    reasons = sorted(set(reasons))
    return L3HardBlockWarning(
        allowed=not reasons,
        tier=tier_value,
        reason_codes=tuple(reasons),
        voice_warning_required=high_tier,
        mtls_binding_required=high_tier,
        warning_message=f"{tier_value.value} mutation requires explicit operator approval and evidence binding.",
    )


def enforce_evolution_mutation(
    tier: EvolutionTier | str,
    *,
    evidence_refs: list[str] | tuple[str, ...] = (),
    explicit_approval: bool = False,
    mtls_enabled: bool = False,
) -> EvolutionMutationDecision:
    """Single runtime guard for ontology mutations before execution starts."""
    forgetting = decide_forgetting(tier, evidence_refs=evidence_refs, explicit_approval=explicit_approval)
    warning = build_l3_hard_block_warning(tier, reason_codes=forgetting.reason_codes, mtls_enabled=mtls_enabled)
    reasons = tuple(sorted(set((*forgetting.reason_codes, *warning.reason_codes))))
    return EvolutionMutationDecision(
        allowed=forgetting.allowed and warning.allowed,
        tier=EvolutionTier(tier),
        forgetting=forgetting,
        warning=warning,
        reason_codes=reasons,
    )


def audit_shadow_isolation(
    shadow_rows: list[dict[str, Any]],
    *,
    production_roots: list[str] | tuple[str, ...],
) -> ShadowIsolationDecision:
    """Fail closed when a shadow row targets a production path."""
    roots = [Path(item).expanduser().resolve() for item in production_roots if str(item).strip()]
    reasons: list[str] = []
    for row in shadow_rows:
        target = str(row.get("target_path") or row.get("write_path") or "").strip()
        if not target:
            continue
        resolved = Path(target).expanduser().resolve()
        if any(resolved == root or root in resolved.parents for root in roots):
            reasons.append("shadow_target_inside_production_root")
    return ShadowIsolationDecision(
        isolated=not reasons,
        production_write_allowed=False,
        reason_codes=tuple(sorted(set(reasons))),
    )


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
