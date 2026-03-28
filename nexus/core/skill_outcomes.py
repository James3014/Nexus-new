from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


EVENTS_REL_PATH = Path(".nexus/metrics/skill_outcome_events.jsonl")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def build_outcome_event(
    *,
    task_id: str,
    phase: str,
    decision_id: str,
    skill_id: str,
    passed: bool,
    phantom_blocked: bool,
    repair_success: bool,
    retry_count: int,
    proof_present: bool,
    regression_pass_rate: float,
    pattern_reuse: float,
    next_run_hit: float,
    metadata: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    md = metadata or {}
    fail = not passed
    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "task_id": str(task_id),
        "phase": str(phase),
        "decision_id": str(decision_id),
        "skill_id": str(skill_id),
        "pass": bool(passed),
        "fail": bool(fail),
        "phantom_blocked": bool(phantom_blocked),
        "regression_pass_rate": _safe_float(regression_pass_rate),
        "self_heal_retry_count": int(max(0, retry_count)),
        # Anti-hallucination signals
        "proof_present": bool(proof_present),
        # Self-healing signals
        "repair_success": bool(repair_success),
        "retry_count": int(max(0, retry_count)),
        # Learning signals
        "pattern_reuse": _safe_float(pattern_reuse),
        "next_run_hit": _safe_float(next_run_hit),
        # Optional enrichments
        "status": str(md.get("status", "")),
        "audit_status": str(md.get("audit_status", "")),
        "source": str(md.get("source", "pipeline")),
    }


def append_skill_outcome_event(project_root: Path, event: Dict[str, Any]) -> Path:
    output_path = project_root / EVENTS_REL_PATH
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False))
        handle.write("\n")
    return output_path
