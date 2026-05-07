from __future__ import annotations

from typing import Any

HIGH_COST_CAPABILITIES = {
    "research",
    "external_doc_scout",
    "ultra_review",
    "sandbox",
    "swarm",
    "nightshift",
    "research_control_plane",
}

CONTRACT_SPLITTER = "\n\nNexus wearing contract:"


def task_body_only(task_desc: str) -> str:
    return (task_desc or "").split(CONTRACT_SPLITTER, 1)[0]


def build_route_misclassification_audit(
    *,
    task_desc: str,
    task_type: str,
    plan: Any,
    recommended_flow: str,
) -> dict[str, Any]:
    normalized_task_desc = task_body_only(task_desc)
    selected = [str(item) for item in getattr(plan, "selected_capabilities", []) or [] if str(item).strip()]
    decision_trace = list(getattr(plan, "decision_trace", []) or [])
    trace_by_capability = {
        str(item.get("capability")): item
        for item in decision_trace
        if isinstance(item, dict) and str(item.get("capability", "")).strip()
    }
    high_cost_selected = [name for name in selected if name in HIGH_COST_CAPABILITIES]
    bounded_repair_profile = (
        "repair" in str(task_type).lower()
        and recommended_flow == "hyper_sprint"
        and not high_cost_selected
    )
    suspicious_reasons: list[dict[str, Any]] = []
    for capability in high_cost_selected:
        reasons = [str(item) for item in (trace_by_capability.get(capability, {}) or {}).get("reasons", []) or []]
        suspicious = any(
            reason
            in {
                "context_or_retrieval_gap",
                "doc_scout_hits_available_for_external_verification",
                "high_risk_or_governance_route",
            }
            for reason in reasons
        )
        if suspicious:
            suspicious_reasons.append(
                {
                    "capability": capability,
                    "reasons": reasons,
                }
            )
    return {
        "schema_version": "nexus_route_misclassification_audit_v1",
        "task_body_used_for_lexical_signals": normalized_task_desc != (task_desc or ""),
        "normalized_task_desc": normalized_task_desc,
        "contract_suffix_detected": CONTRACT_SPLITTER in (task_desc or ""),
        "bounded_repair_profile": bounded_repair_profile,
        "high_cost_capabilities_selected": high_cost_selected,
        "high_cost_selected_count": len(high_cost_selected),
        "suspicious_high_cost_reasons": suspicious_reasons,
    }
