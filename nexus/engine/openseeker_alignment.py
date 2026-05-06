from __future__ import annotations

from collections.abc import Iterable
from typing import Any

MIN_EVOLUTION_STEPS = 10


def _refs_from_receipts(receipts: Iterable[dict[str, Any]]) -> list[str]:
    refs: list[str] = []
    for receipt in receipts:
        for ref in receipt.get("evidence_refs", []) or []:
            text = str(ref).strip()
            if text:
                refs.append(text)
    return sorted(set(refs))


def _source_kind(ref: str) -> str:
    lowered = ref.lower()
    if lowered.startswith("semantic:"):
        return "semantic"
    if lowered.startswith("external:") or "external_doc_scout" in lowered:
        return "external"
    if "codeintel" in lowered or lowered.endswith(".py"):
        return "code"
    if "formal" in lowered or lowered.endswith(".md"):
        return "report"
    if "asi" in lowered or "constraint" in lowered:
        return "asi"
    return "artifact"


def _belief_confidence(usage_trace: dict[str, Any]) -> tuple[float | None, str]:
    capabilities = usage_trace.get("capabilities", {}) if isinstance(usage_trace.get("capabilities"), dict) else {}
    if capabilities.get("belief_confidence") is not None:
        return float(capabilities.get("belief_confidence") or 0.0), "capabilities.belief_confidence"
    route_decision = usage_trace.get("route_decision", {}) if isinstance(usage_trace.get("route_decision"), dict) else {}
    signal_snapshot = route_decision.get("signal_snapshot", {}) if isinstance(route_decision.get("signal_snapshot"), dict) else {}
    if signal_snapshot.get("confidence") is not None:
        return float(signal_snapshot.get("confidence") or 0.0), "route_decision.signal_snapshot.confidence"
    pillars = usage_trace.get("pillars", {}) if isinstance(usage_trace.get("pillars"), dict) else {}
    belief = pillars.get("belief", {}) if isinstance(pillars.get("belief"), dict) else {}
    if belief.get("confidence") is not None:
        return float(belief.get("confidence") or 0.0), "pillars.belief.confidence"
    return None, ""


def build_openseeker_trace(
    *,
    usage_trace: dict[str, Any],
    capability_receipts: list[dict[str, Any]],
) -> dict[str, Any]:
    phase_trace = usage_trace.get("phase_trace", {}) if isinstance(usage_trace.get("phase_trace"), dict) else {}
    capabilities = usage_trace.get("capabilities", {}) if isinstance(usage_trace.get("capabilities"), dict) else {}
    route_decision = usage_trace.get("route_decision", {}) if isinstance(usage_trace.get("route_decision"), dict) else {}
    stop_policy = route_decision.get("stop_policy", {}) if isinstance(route_decision.get("stop_policy"), dict) else {}
    selected = list(route_decision.get("selected_capabilities", []) or [])
    if not selected:
        capability_plan = usage_trace.get("capability_plan", {}) if isinstance(usage_trace.get("capability_plan"), dict) else {}
        selected = list(capability_plan.get("selected_capabilities", []) or [])
    tactical_sequence = [
        str(item).strip()
        for item in (stop_policy.get("tactical_sequence", []) or [])
        if str(item).strip()
    ]
    tactical_tool_map = stop_policy.get("tactical_tool_map", []) if isinstance(stop_policy.get("tactical_tool_map"), list) else []
    refs = _refs_from_receipts([item for item in capability_receipts if isinstance(item, dict)])
    source_kinds = sorted({_source_kind(ref) for ref in refs})
    belief_confidence, belief_source = _belief_confidence(usage_trace)
    action_sequence = [f"phase:{phase}" for phase, status in sorted(phase_trace.items()) if str(status).strip()]
    action_sequence.extend(f"tactical:{name}" for name in tactical_sequence)
    action_sequence.extend(f"capability:{name}" for name in selected if str(name).strip())
    tool_action_names = tactical_sequence or selected
    trace = {
        "schema_version": "nexus_openseeker_alignment.v1",
        "min_evolution_steps": MIN_EVOLUTION_STEPS,
        "trajectory_step_count": len(action_sequence),
        "tool_action_count": len(tool_action_names),
        "route_tactical_sequence": tactical_sequence,
        "route_tactical_tool_count": len(tactical_tool_map),
        "route_evidence_required_count": sum(1 for item in tactical_tool_map if isinstance(item, dict) and bool(item.get("evidence_required"))),
        "evidence_hop_count": len(refs),
        "evidence_source_count": len(source_kinds),
        "evidence_source_kinds": source_kinds,
        "action_sequence": action_sequence,
        "low_step_filtered": len(action_sequence) < MIN_EVOLUTION_STEPS,
        "single_source_claim": bool(capabilities.get("claim_verified", False) and len(source_kinds) < 2),
    }
    if belief_confidence is not None:
        trace["belief_confidence_at_decision"] = max(0.0, min(1.0, belief_confidence))
        trace["belief_confidence_source"] = belief_source
        trace["belief_low_confidence"] = trace["belief_confidence_at_decision"] < 0.6
    trace["long_horizon_ready"] = bool(
        not trace["low_step_filtered"]
        and trace["evidence_hop_count"] >= 2
        and trace["tool_action_count"] >= 2
    )
    return trace


def summarize_receipt_metrics(receipts: Iterable[Any]) -> dict[str, Any]:
    normalized = []
    for receipt in receipts:
        if hasattr(receipt, "to_dict"):
            receipt = receipt.to_dict()
        if isinstance(receipt, dict):
            normalized.append(receipt)
    evidence_refs = _refs_from_receipts(normalized)
    return {
        "schema_version": "nexus_openseeker_receipt_metrics.v1",
        "tool_action_count": sum(1 for item in normalized if bool(item.get("invoked", False))),
        "evidence_hop_count": len(evidence_refs),
        "evidence_source_count": len({_source_kind(ref) for ref in evidence_refs}),
    }
