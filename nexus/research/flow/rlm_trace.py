from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from nexus.contracts import RLMTraceEvent, RLMTraceWriter


def safe_trace_slug(text: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", (text or "").strip().lower()).strip("-")
    return slug[:80] or "research-auto-flow"


def write_research_rlm_trace(
    *,
    repo_root: Path,
    task_desc: str,
    result: dict[str, Any],
    nexus_usage_trace: dict[str, Any],
    artifact_summary: dict[str, Any],
    recursive_research: bool = False,
) -> str:
    trace_path = repo_root / ".nexus" / "reports" / "rlm_trace" / f"{safe_trace_slug(task_desc)}.jsonl"
    writer = RLMTraceWriter(trace_path)
    task_id = safe_trace_slug(task_desc)
    report = result.get("report", {}) if isinstance(result.get("report"), dict) else {}
    confidence = float(((nexus_usage_trace.get("pillars", {}) or {}).get("belief", {}) or {}).get("confidence", 0.0) or 0.0)
    confidence = max(0.0, min(1.0, confidence))
    parent_iteration_id = ""
    if recursive_research:
        parent_iteration_id = "x-1"
        writer.append(
            RLMTraceEvent(
                task_id=task_id,
                phase="X",
                iteration_id="x-1",
                action_type="research_candidate",
                observation=str(report.get("winner_source") or result.get("status", "")),
                confidence=confidence,
                allowed_tools=["research:auto-flow", "code:impact", "learn:ask"],
                policy_reason="recursive_research_candidate",
                stop_reason="candidate_selected",
                artifact_refs=[str(report.get("report_file", ""))] if report.get("report_file") else [],
            )
        )
    writer.append(
        RLMTraceEvent(
            task_id=task_id,
            phase="R",
            iteration_id="r-1",
            parent_iteration_id=parent_iteration_id,
            action_type="research_auto_flow",
            observation=str(result.get("status", "")),
            confidence=confidence,
            allowed_tools=[
                "research:auto-flow",
                "hyper_sprint" if nexus_usage_trace.get("capabilities", {}).get("hyper_used") else "baseline",
            ],
            policy_reason="research_auto_flow_bridge",
            stop_reason="submit",
            artifact_refs=[str(report.get("winner_source", ""))] if report.get("winner_source") else [],
        )
    )
    writer.append(
        RLMTraceEvent(
            task_id=task_id,
            phase="A",
            iteration_id="a-1",
            parent_iteration_id="r-1",
            action_type="audit",
            observation="verified" if artifact_summary.get("tests_passed") else "unverified",
            blocked_reason="" if artifact_summary.get("tests_passed") else "tests_failed",
            stop_reason="verified" if artifact_summary.get("tests_passed") else "audit_rejected",
        )
    )
    return str(trace_path)
