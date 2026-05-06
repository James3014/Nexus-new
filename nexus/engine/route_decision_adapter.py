from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nexus.engine.capability_contracts import CapabilityPlan, RouteDecision
from nexus.engine.capability_executor_controls import build_execution_plan


def _hash_task_desc(task_desc: str) -> str:
    return hashlib.sha256((task_desc or "").encode("utf-8")).hexdigest()[:16]


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


def _default_stop_policy(plan: CapabilityPlan, recommended_flow: str, stop_policy: dict[str, Any] | None) -> dict[str, Any]:
    policy = dict(stop_policy or {"type": "receipt_backed", "budget_guard": "fail_closed"})
    selected = [str(item) for item in plan.selected_capabilities if str(item).strip()]
    preferred = [
        "pregate",
        "memory",
        "lancedb",
        "semantic_searcher",
        "research",
        "external_doc_scout",
        "codeintel",
        "hyper",
        "autoreason",
        "judge_panel",
        "llm_judge_panel",
        "ddtree",
        "belief",
        "ultra_review",
        "formal_report",
        "delivery_gate",
        "claim_gate",
        "swarm_quiet_moment",
    ]
    first = "hyper_sprint" if recommended_flow == "hyper_sprint" or "hyper" in selected else "baseline"
    tactical_sequence = [first]
    tactical_sequence.extend(name for name in preferred if name in selected)
    tactical_sequence.extend(name for name in selected if name not in tactical_sequence)
    tactical_sequence = list(dict.fromkeys(tactical_sequence))

    from nexus.engine.capability_planner import default_capability_nodes

    nodes = default_capability_nodes()
    tactical_tool_map = []
    for index, name in enumerate(tactical_sequence):
        node = nodes.get(name)
        tactical_tool_map.append(
            {
                "capability": name,
                "after": tactical_sequence[index - 1] if index else None,
                "purpose": "gather_evidence" if name in {"semantic_searcher", "external_doc_scout", "research", "lancedb", "codeintel"} else "verify_or_govern",
                "evidence_required": bool(node and node.evidence_outputs),
            }
        )
    policy.setdefault("tactical_sequence", tactical_sequence)
    policy.setdefault("tactical_tool_map", tactical_tool_map)
    return policy


def build_route_decision(
    *,
    task_id: str,
    task_desc: str,
    task_type: str,
    recommended_flow: str,
    plan: CapabilityPlan,
    stop_policy: dict[str, Any] | None = None,
    tuning_snapshot: dict[str, Any] | None = None,
) -> RouteDecision:
    execution = build_execution_plan(plan)
    selected = tuple(plan.selected_capabilities)
    acceleration = tuple(item for item in ("ddtree",) if item in selected)
    governance = tuple(item for item in ("ultra_review", "mempalace_gate", "artifact_gate", "claim_gate") if item in selected)
    signal_snapshot = dict(plan.signal_snapshot)
    signal_snapshot["pillar_signals"] = build_pillar_signal_summary(plan)
    forecast_gate_shadow = build_forecast_gate_shadow(plan)
    routing_tier = str(signal_snapshot.get("routing_tier", "") or "")
    routing_tier_reason = str(signal_snapshot.get("routing_tier_reason", "") or "")
    routing_tier_fallback_used = False
    if not routing_tier:
        routing_tier_fallback_used = True
        routing_tier = str(forecast_gate_shadow.get("suggested_tier", "L2_context_governed"))
        routing_tier_reason = str(forecast_gate_shadow.get("suggested_tier_reason", "forecast_gate_default"))
    hazard_hits = tuple(str(item) for item in (signal_snapshot.get("hazard_hits", []) or []) if str(item))
    hazard_forced_l3 = bool(signal_snapshot.get("hazard_forced_l3", False))
    policy_loaded_count = int(signal_snapshot.get("policy_loaded_count", 0) or 0)
    policy_pruned_count = int(signal_snapshot.get("policy_pruned_count", 0) or 0)
    early_exit_used = bool(forecast_gate_shadow.get("early_exit_candidate", False) and routing_tier == "L1_green_lane")
    plan_recommended_flow = str(signal_snapshot.get("recommended_flow", "") or "")
    recommended_flow_mismatch = bool(plan_recommended_flow and plan_recommended_flow != recommended_flow)
    derivation_meta = {
        "routing_tier_fallback_used": routing_tier_fallback_used,
        "recommended_flow_mismatch": recommended_flow_mismatch,
        "recommended_flow_param": recommended_flow,
        "recommended_flow_plan": plan_recommended_flow,
        "acceleration_layers_rule": "selected_capabilities_intersection_ddtree",
        "governance_layers_rule": "selected_capabilities_intersection_ultra_mempalace_artifact_claim",
    }
    resolved_stop_policy = _default_stop_policy(plan, recommended_flow, stop_policy)
    return RouteDecision(
        schema_version="nexus_route_decision_v1",
        plan_schema_version=plan.schema_version,
        plan_mode=plan.planner_mode,
        plan_score=int(plan.score),
        task_id=task_id,
        task_type=task_type,
        task_desc_hash=_hash_task_desc(task_desc),
        recommended_flow=recommended_flow,
        decision_source="capability_planner",
        signal_snapshot=signal_snapshot,
        selected_capabilities=selected,
        required_capabilities=tuple(plan.required_capabilities),
        conditional_capabilities=tuple(plan.conditional_capabilities),
        pending_capabilities=tuple(plan.pending_capabilities),
        forbidden_capabilities=tuple(plan.forbidden_capabilities),
        acceleration_layers=acceleration,
        governance_layers=governance,
        executor_controls=dict(execution.executor_controls),
        constraints=tuple(plan.constraints),
        decision_trace=tuple(plan.decision_trace),
        stop_policy=resolved_stop_policy,
        receipt_requirements=("invoked", "evidence_present", "gate_passed", "outcome_contributed"),
        fallback_policy="fail_closed",
        forecast_gate_shadow=forecast_gate_shadow,
        routing_tier=routing_tier,
        routing_tier_reason=routing_tier_reason,
        hazard_hits=hazard_hits,
        hazard_forced_l3=hazard_forced_l3,
        early_exit_used=early_exit_used,
        policy_loaded_count=policy_loaded_count,
        policy_pruned_count=policy_pruned_count,
        tuning_snapshot=tuning_snapshot or {},
        derivation_meta=derivation_meta,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def write_route_decision_report(path: Path, decision: RouteDecision) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(decision.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    return path
