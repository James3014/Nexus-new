from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CapabilityDecision:
    selected_capabilities: list[str]
    acceleration_layers: list[str]
    governance_layers: list[str]
    explain_caps: list[dict[str, Any]]
    stop_policy: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "selected_capabilities": self.selected_capabilities,
            "acceleration_layers": self.acceleration_layers,
            "governance_layers": self.governance_layers,
            "explain_caps": self.explain_caps,
            "stop_policy": self.stop_policy,
        }


class CapabilityRouter:
    """Compatibility facade that exposes the legacy capability_stack schema."""

    HIGH_RISK_PREFIXES = (
        "nexus/engine/",
        "nexus/orchestrator/",
        "nexus/research/",
        "nexus/security/",
        "scripts/engine/",
        "scripts/ops/",
    )

    def route(
        self,
        *,
        task_desc: str,
        task_type: str,
        recommended_flow: str,
        route_features: dict[str, Any],
        target_file: str | None = None,
    ) -> CapabilityDecision:
        from nexus.engine.capability_selector import CapabilitySelector

        task_lower = f"{task_desc} {task_type}".lower()
        seed_selected = ["hyper_sprint"] if recommended_flow == "hyper_sprint" else ["baseline"]
        readiness = route_features.get("candidate_factory_readiness_estimate", {})
        readiness = readiness if isinstance(readiness, dict) else {}
        estimated_candidates = int(readiness.get("estimated_candidates", route_features.get("candidate_count", 1)) or 1)
        candidate_factory_ready = bool(readiness.get("ready", estimated_candidates >= 2))
        seed_acceleration = ["ddtree"] if candidate_factory_ready and estimated_candidates >= 3 else []
        if any(str(target_file or "").startswith(prefix) for prefix in self.HIGH_RISK_PREFIXES):
            route_features = {**route_features, "has_hard_signal": True}
        plan = CapabilitySelector().select(
            task_desc=task_desc,
            task_type=task_type,
            route={
                "recommended_flow": recommended_flow,
                "route_features": route_features,
                "route_decision": {
                    "selected_capabilities": seed_selected,
                    "acceleration_layers": seed_acceleration,
                    "governance_layers": [],
                },
            },
        )
        planned = set(plan.selected_capabilities)
        planned_order = [name for name in plan.selected_capabilities if isinstance(name, str) and name.strip()]
        selected = ["hyper_sprint"] if "hyper" in planned else ["baseline"]
        if "autoreason" in planned:
            selected.append("autoreason")
        ddtree_enabled = "ddtree" in planned
        ultra_enabled = "ultra_review" in planned

        def _reasons(capability: str) -> list[str]:
            for item in plan.decision_trace:
                if item.get("capability") == capability:
                    return list(item.get("reasons", []) or [])
            return []

        def _tactical_sequence() -> list[str]:
            deep_route = bool(
                candidate_factory_ready
                or route_features.get("has_hard_signal")
                or float(route_features.get("risk_score", 0.0) or 0.0) >= 40.0
                or route_features.get("is_cross_module_task")
            )
            if route_features.get("is_doc_fix") and not deep_route:
                return ["baseline"]
            preferred = [
                "pregate",
                "memory",
                "lancedb",
                "semantic_searcher",
                "research",
                "external_doc_scout",
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
            ordered = ["hyper_sprint" if recommended_flow == "hyper_sprint" else "baseline"]
            ordered.extend(name for name in preferred if name in planned)
            ordered.extend(name for name in planned_order if name not in ordered)
            return list(dict.fromkeys(ordered))

        tactical_sequence = _tactical_sequence()
        tactical_tool_map = [
            {
                "capability": name,
                "after": tactical_sequence[index - 1] if index else None,
                "purpose": "gather_evidence" if name in {"semantic_searcher", "external_doc_scout", "research", "lancedb"} else "verify_or_govern",
                "evidence_required": name
                in {
                    "semantic_searcher",
                    "external_doc_scout",
                    "autoreason",
                    "judge_panel",
                    "llm_judge_panel",
                    "belief",
                    "formal_report",
                    "delivery_gate",
                    "claim_gate",
                },
            }
            for index, name in enumerate(tactical_sequence)
        ]

        explain = [
            {
                "capability": "hyper_sprint" if recommended_flow == "hyper_sprint" else "baseline",
                "enabled": True,
                "reasons": [f"recommended_flow:{recommended_flow}"],
                "evidence": ["route.recommended_flow"],
            },
            {
                "capability": "autoreason",
                "enabled": "autoreason" in planned,
                "reasons": _reasons("autoreason"),
                "evidence": ["capability_plan.decision_trace"],
            },
            {
                "capability": "ddtree",
                "enabled": ddtree_enabled,
                "reasons": _reasons("ddtree"),
                "evidence": ["capability_plan.decision_trace"],
            },
            {
                "capability": "ultra_review",
                "enabled": ultra_enabled,
                "reasons": _reasons("ultra_review"),
                "evidence": ["capability_plan.decision_trace"],
            },
        ]
        return CapabilityDecision(
            selected_capabilities=selected,
            acceleration_layers=["ddtree"] if ddtree_enabled else [],
            governance_layers=["ultra_review"] if ultra_enabled else [],
            explain_caps=explain,
            stop_policy={
                "type": "a_streak" if "autoreason" in planned else "budget",
                "threshold": 2 if "autoreason" in planned else 1,
                "budget_guard": "fail_closed",
                "tactical_sequence": tactical_sequence,
                "tactical_tool_map": tactical_tool_map,
            },
        )
