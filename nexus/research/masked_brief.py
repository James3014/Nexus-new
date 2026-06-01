from __future__ import annotations

import re
from typing import Any

from nexus.research.isolation_contracts import MaskedResearchBrief, ResearchIsolationDecision, ResearchGoalVisibility


def build_masked_research_brief(
    *,
    task_desc: str,
    metadata: dict[str, Any] | None,
    decision: ResearchIsolationDecision,
) -> MaskedResearchBrief:
    metadata = metadata or {}
    
    # 提取基本事實 (Facts Only)
    scope = tuple(_as_list(metadata.get("target_files")))
    symbols = tuple(_as_list(metadata.get("target_symbols")))
    trace = tuple(_as_list(metadata.get("process_names")))
    observed = tuple(_as_list(metadata.get("observed_behavior")) or _extract_observed_behavior(task_desc))
    
    return MaskedResearchBrief(
        scope=scope,
        symbols=symbols,
        trace=trace,
        observed_behavior=observed,
        
        # Metadata for audit
        task_label=str(metadata.get("task_id") or "masked-research-task"),
        allowed_sources=decision.allowed_sources,
        forbidden_fields_removed=decision.forbidden_fields,
        goal_visibility=decision.goal_visibility.value,
    )


def brief_to_research_task(brief: MaskedResearchBrief) -> str:
    sections = [
        f"Masked research brief: {brief.task_label}",
        f"Goal visibility: {brief.goal_visibility}",
        f"Allowed sources: {', '.join(brief.allowed_sources)}",
        f"Target scope: {', '.join(brief.scope) or 'unknown'}",
        f"Key symbols: {', '.join(brief.symbols) or 'unknown'}",
        f"Observed behavior: {'; '.join(brief.observed_behavior) or 'unknown'}",
        f"Traces: {'; '.join(brief.trace) or 'none'}",
        "Return facts only. Do not propose designs, patches, fixes, or implementation steps.",
    ]
    return "\n".join(sections)


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _extract_observed_behavior(text: str) -> list[str]:
    lines = [line.strip("-: \t") for line in (text or "").splitlines() if line.strip()]
    observed = []
    for line in lines:
        match = re.search(r"(observed[^。.\n]*(?:error|failure|timeout)[^。.\n]*)", line, re.IGNORECASE)
        if match:
            observed.append(match.group(1).strip())
    safe = [
        line
        for line in lines
        if any(token in line.lower() for token in ("error", "failed", "failure", "timeout", "observed", "trace"))
    ]
    return (observed or safe)[:5]
