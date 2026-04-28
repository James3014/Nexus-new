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
    """Build an explainable Nexus capability stack without changing execution paths."""

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
        selected = ["hyper_sprint"] if recommended_flow == "hyper_sprint" else ["baseline"]
        risk_score = int(route_features.get("risk_score", 0) or 0)
        confidence = float(route_features.get("adjusted_root_cause_confidence", 1.0) or 1.0)
        candidate_count = int(route_features.get("candidate_count", 1) or 1)
        findings_hits = int(route_features.get("findings_hits", 0) or 0)
        memory_hits = int(route_features.get("memory_hits", 0) or 0)
        task_lower = (task_desc or "").lower()
        is_cross_module = bool(route_features.get("is_cross_module_task", False))
        has_hard_signal = bool(route_features.get("has_hard_signal", False))

        autoreason_reasons: list[str] = []
        if recommended_flow == "hyper_sprint":
            autoreason_reasons.append("hyper_sprint_route")
        if confidence < 0.75:
            autoreason_reasons.append("low_confidence")
        if findings_hits > 0 or memory_hits > 0:
            autoreason_reasons.append("historical_signal")
        if is_cross_module or any(token in task_lower for token in ("hard", "race", "deadlock", "timeout", "cross-module")):
            autoreason_reasons.append("hard_or_cross_module")
        autoreason_enabled = bool(autoreason_reasons)
        if autoreason_enabled and "autoreason" not in selected:
            selected.append("autoreason")

        ddtree_reasons: list[str] = []
        if autoreason_enabled and candidate_count >= 3:
            ddtree_reasons.append("autoreason_candidate_budget")
        if "token" in task_lower or "multi-round" in task_lower:
            ddtree_reasons.append("high_token_or_multi_round")
        ddtree_enabled = bool(ddtree_reasons)

        target = target_file or ""
        ultra_reasons: list[str] = []
        if risk_score >= 70:
            ultra_reasons.append("high_risk_score")
        if is_cross_module or has_hard_signal:
            ultra_reasons.append("cross_module_or_hard_signal")
        if any(target.startswith(prefix) for prefix in self.HIGH_RISK_PREFIXES):
            ultra_reasons.append("high_risk_path")
        ultra_enabled = bool(ultra_reasons)

        explain = [
            {
                "capability": "hyper_sprint" if recommended_flow == "hyper_sprint" else "baseline",
                "enabled": True,
                "reasons": [f"recommended_flow:{recommended_flow}"],
                "evidence": ["route.recommended_flow"],
            },
            {
                "capability": "autoreason",
                "enabled": autoreason_enabled,
                "reasons": autoreason_reasons,
                "evidence": ["route_features"],
            },
            {
                "capability": "ddtree",
                "enabled": ddtree_enabled,
                "reasons": ddtree_reasons,
                "evidence": ["candidate_count", "task_desc"],
            },
            {
                "capability": "ultra_review",
                "enabled": ultra_enabled,
                "reasons": ultra_reasons,
                "evidence": ["risk_score", "target_file", "route_features"],
            },
        ]
        return CapabilityDecision(
            selected_capabilities=selected,
            acceleration_layers=["ddtree"] if ddtree_enabled else [],
            governance_layers=["ultra_review"] if ultra_enabled else [],
            explain_caps=explain,
            stop_policy={
                "type": "a_streak" if autoreason_enabled else "budget",
                "threshold": 2 if autoreason_enabled else 1,
                "budget_guard": "fail_closed",
            },
        )
