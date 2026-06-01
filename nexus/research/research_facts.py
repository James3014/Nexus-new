from __future__ import annotations

from typing import Any

from nexus.research.isolation_contracts import ResearchFacts, ResearchIsolationReceipt


DESIGN_FIELD_NAMES = {
    "solution",
    "proposal",
    "patch_plan",
    "implementation_plan",
    "recommended_capabilities",
    "next_action_hint",
    "winner",
}


def build_research_facts(
    *,
    research_pack: dict[str, Any],
    visibility_receipt: dict[str, Any],
) -> ResearchFacts:
    findings = _as_tuple(research_pack.get("findings"))
    refs = _as_tuple(research_pack.get("retrieval_refs") or research_pack.get("research_refs"))
    raw = research_pack.get("raw", {}) if isinstance(research_pack.get("raw"), dict) else {}
    return ResearchFacts(
        observed_components=_as_tuple(raw.get("observed_components") or research_pack.get("observed_components")),
        execution_flows=_as_tuple(raw.get("execution_flows") or research_pack.get("execution_flows")),
        constraints=_as_tuple(research_pack.get("blocked_assumptions")) or findings,
        evidence_refs=refs,
        open_questions=_as_tuple(raw.get("open_questions") or research_pack.get("open_questions")),
        unknowns=_as_tuple(raw.get("unknowns") or research_pack.get("unknowns")),
        visibility_receipt=visibility_receipt,
    )


def build_isolation_receipt(
    *,
    decision: Any,
    guard_result: Any,
    artifact_schema: str,
    artifact_refs: tuple[str, ...],
) -> ResearchIsolationReceipt:
    level = getattr(decision, "level", "")
    level_text = getattr(level, "value", str(level))
    goal_visibility = getattr(decision, "goal_visibility", "")
    goal_visibility_text = getattr(goal_visibility, "value", str(goal_visibility))
    output_mode = getattr(decision, "output_mode", "")
    output_mode_text = getattr(output_mode, "value", str(output_mode))
    return ResearchIsolationReceipt(
        research_masked=goal_visibility_text in {"masked", "none"},
        isolation_level=level_text,
        goal_visibility=goal_visibility_text,
        research_agent_saw_user_goal=goal_visibility_text == "full",
        output_mode=output_mode_text,
        facts_only_guard_passed=bool(getattr(guard_result, "passed", False)),
        design_terms_detected=tuple(getattr(guard_result, "detected_terms", ()) or ()),
        artifact_schema=artifact_schema,
        artifact_refs=artifact_refs,
    )


def has_design_fields(payload: dict[str, Any]) -> bool:
    return bool(DESIGN_FIELD_NAMES & set(payload))


def _as_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (list, tuple, set)):
        return tuple(str(item) for item in value if str(item))
    text = str(value)
    return (text,) if text else ()
