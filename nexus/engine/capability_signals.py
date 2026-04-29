from __future__ import annotations

import re
from typing import Any

from nexus.engine.capability_contracts import CapabilityConstraints, CapabilitySignalSet, SkillSignalSet


def _as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _contains_any(text: str, tokens: tuple[str, ...]) -> bool:
    return any(token in text for token in tokens)


def _contains_word_or_phrase(text: str, tokens: tuple[str, ...]) -> bool:
    for token in tokens:
        if " " in token:
            if token in text:
                return True
            continue
        if re.search(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])", text):
            return True
    return False


def build_skill_signals(skills: list[dict[str, Any]] | None = None) -> SkillSignalSet:
    skills = skills or []
    top_ids = tuple(str(item.get("skill_id") or item.get("task_id") or "") for item in skills[:3])
    confidences = [_as_float(item.get("win_rate", item.get("score", 0.0)), 0.0) for item in skills[:3]]
    return SkillSignalSet(
        top_skill_ids=tuple(item for item in top_ids if item),
        skill_confidence=max(confidences or [0.0]),
        trust_level=str((skills[0] or {}).get("trust_level", "")) if skills else "",
        source=str((skills[0] or {}).get("source", "")) if skills else "",
    )


def build_capability_signals(
    *,
    task_desc: str,
    task_type: str,
    route: dict[str, Any] | None,
    pillars: dict[str, Any] | None = None,
    codeintel: dict[str, Any] | None = None,
    skills: list[dict[str, Any]] | None = None,
) -> CapabilitySignalSet:
    route = route or {}
    pillars = pillars or {}
    codeintel = codeintel or {}
    route_features = route.get("route_features", {}) if isinstance(route, dict) else {}
    capability_stack = route.get("capability_stack", {}) if isinstance(route, dict) else {}
    task_lower = f"{task_desc} {task_type}".lower()
    skill_signals = build_skill_signals(skills)

    return CapabilitySignalSet(
        task_desc=task_desc,
        task_type=task_type,
        recommended_flow=str(route.get("recommended_flow", "") or ""),
        selected_seed=tuple(str(item) for item in capability_stack.get("selected_capabilities", []) or []),
        acceleration_seed=tuple(str(item) for item in capability_stack.get("acceleration_layers", []) or []),
        governance_seed=tuple(str(item) for item in capability_stack.get("governance_layers", []) or []),
        risk_score=_as_int(route_features.get("risk_score"), 0),
        confidence=_as_float(route_features.get("adjusted_root_cause_confidence"), 1.0),
        candidate_count=max(1, _as_int(route_features.get("candidate_count"), 1)),
        memory_hits=_as_int(route_features.get("memory_hits"), 0),
        findings_hits=_as_int(route_features.get("findings_hits"), 0),
        lancedb_hits=_as_int((pillars.get("lancedb", {}) or {}).get("hits"), 0),
        cross_module=bool(route_features.get("is_cross_module_task", False)),
        hard_signal=bool(route_features.get("has_hard_signal", False)),
        codeintel_impact_present=bool(codeintel.get("impact_report_present", False)),
        should_research=bool(route.get("should_research", False)),
        governance_signal=_contains_any(
            task_lower,
            ("secret", "credential", "redact", "auth", "authorization", "deny by default", "governance"),
        ),
        evidence_signal=_contains_any(task_lower, ("evidence", "artifact", "claim", "semantic", "trust")),
        repair_signal=_contains_any(task_lower, ("repair", "self-heal", "failing branch", "timeout", "flaky")),
        learning_signal=_contains_any(task_lower, ("learn", "citation", "slo", "kpi", "source", "claim")),
        multi_agent_signal=_contains_any(task_lower, ("multi-agent", "owner", "file lock", "worktree", "integrate")),
        swarm_signal="swarm" in task_lower,
        drone_signal="drone" in task_lower or "parallel" in task_lower or "split" in task_lower,
        nightshift_signal="nightshift" in task_lower,
        ui_signal=_contains_word_or_phrase(
            task_lower,
            ("ui", "user interface", "browser", "screen", "accessibility", "visual"),
        ),
        continuity_signal=_contains_any(task_lower, ("resume", "distill", "checkpoint", "metabolism")),
        benchmark_signal="benchmark" in task_lower or "public report" in task_lower,
        meta_opt_signal="meta-opt" in task_lower or "autotune" in task_lower,
        registry_signal="registry" in task_lower or "skill" in task_lower,
        oracle_signal="oracle" in task_lower or "shadow" in task_lower,
        federation_signal="federation" in task_lower or "tenant" in task_lower,
        stress_signal="stress" in task_lower or "recursion" in task_lower,
        skill_candidates=skill_signals.top_skill_ids,
        skill_confidence=skill_signals.skill_confidence,
    )


def build_capability_constraints(budget: dict[str, Any] | None = None) -> CapabilityConstraints:
    budget = budget or {}
    return CapabilityConstraints(max_cost=max(1, _as_int(budget.get("max_cost"), 999)))
