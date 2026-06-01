from __future__ import annotations

import re
from typing import Any

from nexus.research.isolation_contracts import MaskedResearchBrief, ResearchIsolationDecision


def build_masked_research_brief(
    *,
    task_desc: str,
    metadata: dict[str, Any] | None,
    decision: ResearchIsolationDecision,
) -> MaskedResearchBrief:
    metadata = metadata or {}
    return MaskedResearchBrief(
        task_label=str(metadata.get("task_id") or "masked-research-task"),
        observed_behavior=tuple(_as_list(metadata.get("observed_behavior")) or _extract_observed_behavior(task_desc)),
        target_files=tuple(_as_list(metadata.get("target_files"))),
        target_symbols=tuple(_as_list(metadata.get("target_symbols"))),
        process_names=tuple(_as_list(metadata.get("process_names"))),
        error_strings=tuple(_as_list(metadata.get("error_strings")) or _extract_error_strings(task_desc)),
        test_failures=tuple(_as_list(metadata.get("test_failures"))),
        research_questions=tuple(_as_list(metadata.get("research_questions")) or _default_questions()),
        allowed_sources=decision.allowed_sources,
        forbidden_fields_removed=decision.forbidden_fields,
        goal_visibility=decision.goal_visibility.value,
    )


def brief_to_research_task(brief: MaskedResearchBrief) -> str:
    sections = [
        f"Masked research brief: {brief.task_label}",
        f"Goal visibility: {brief.goal_visibility}",
        f"Allowed sources: {', '.join(brief.allowed_sources)}",
        f"Target files: {', '.join(brief.target_files) or 'unknown'}",
        f"Target symbols: {', '.join(brief.target_symbols) or 'unknown'}",
        f"Observed behavior: {'; '.join(brief.observed_behavior) or 'unknown'}",
        f"Errors: {'; '.join(brief.error_strings) or 'none'}",
        f"Test failures: {'; '.join(brief.test_failures) or 'none'}",
        "Research questions:",
        *[f"- {item}" for item in brief.research_questions],
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


def _extract_error_strings(text: str) -> list[str]:
    matches = re.findall(r"([A-Za-z_]*(?:Error|Exception|Failure):?[^\n。]*)", text or "")
    return [item.strip() for item in matches[:5] if item.strip()]


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


def _default_questions() -> list[str]:
    return [
        "Which components and execution flows are involved?",
        "What constraints are visible from code, tests, traces, or docs?",
        "Which facts are evidenced and which points remain unknown?",
    ]
