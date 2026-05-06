from __future__ import annotations

from typing import Any

from nexus.engine.capability_contracts import CapabilityPlan


def build_pillar_signal_summary(plan: CapabilityPlan) -> dict[str, dict[str, Any]]:
    snapshot = dict(plan.signal_snapshot)
    selected = set(plan.selected_capabilities)
    return {
        "LanceDB": {
            "active": bool(snapshot.get("lancedb_hits", 0) or "lancedb" in selected),
            "evidence": ["signal_snapshot.lancedb_hits", "selected_capabilities.lancedb"],
        },
        "Memory": {
            "active": bool(snapshot.get("memory_hits", 0) or snapshot.get("findings_hits", 0) or "memory" in selected),
            "evidence": ["signal_snapshot.memory_hits", "signal_snapshot.findings_hits", "selected_capabilities.memory"],
        },
        "MemPalace": {
            "active": "mempalace_gate" in selected,
            "evidence": ["selected_capabilities.mempalace_gate"],
        },
        "Belief": {
            "active": bool("belief" in selected or float(snapshot.get("confidence", 1.0) or 1.0) < 0.8),
            "evidence": ["selected_capabilities.belief", "signal_snapshot.confidence"],
        },
        "Artifact": {
            "active": "artifact_gate" in selected,
            "evidence": ["selected_capabilities.artifact_gate"],
        },
        "Claim": {
            "active": "claim_gate" in selected,
            "evidence": ["selected_capabilities.claim_gate"],
        },
    }


def build_forecast_gate_shadow(plan: CapabilityPlan) -> dict[str, Any]:
    snapshot = dict(plan.signal_snapshot)
    risk_score = int(snapshot.get("risk_score_0_100", snapshot.get("risk_score", 0)) or 0)
    confidence = float(snapshot.get("confidence", 1.0) or 1.0)
    memory_hits = int(snapshot.get("memory_hits", 0) or 0) + int(snapshot.get("findings_hits", 0) or 0)
    hazard_forced_l3 = bool(snapshot.get("hazard_forced_l3", False))
    selected = set(plan.selected_capabilities)

    if hazard_forced_l3:
        suggested_tier = "L3_full_governed"
        reason = "hazard_mapping_forced_l3"
    elif risk_score >= 70 or "ultra_review" in selected:
        suggested_tier = "L3_full_governed"
        reason = "high_risk_or_ultra_review_selected"
    elif risk_score >= 30 or "codeintel" in selected or "research" in selected:
        suggested_tier = "L2_context_governed"
        reason = "medium_risk_or_context_needed"
    else:
        suggested_tier = "L1_light_governed"
        reason = "low_risk_light_route_candidate"

    early_exit_candidate = bool(
        suggested_tier == "L1_light_governed"
        and confidence >= 0.95
        and memory_hits > 0
        and not hazard_forced_l3
        and not plan.pending_capabilities
    )
    return {
        "schema": "nexus_forecast_gate_shadow_v1",
        "shadow_mode": True,
        "suggested_tier": suggested_tier,
        "suggested_tier_reason": reason,
        "early_exit_candidate": early_exit_candidate,
        "early_exit_policy": "never_skip_mempalace_artifact_claim_delivery_gates",
        "risk_score_0_100": risk_score,
        "confidence": confidence,
    }
