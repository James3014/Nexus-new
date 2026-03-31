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


from dataclasses import dataclass

@dataclass
class OutcomePayload:
    """R1: build_outcome_event 的參數物件。

    標準來源值集合 (source registry):
    - pipeline.crystallize: 正式結晶生產路徑 (預設)
    - pipeline.repair: 正式修復生產路徑
    - pipeline.repair_audit: 治理層 audit 產出 (如 Phantom Gate)
    - calibration.sim: 校準、Soak Test 或模擬訊號
    - research.eval: 基準測試或實驗評估
    """
    task_id: str
    phase: str
    decision_id: str
    skill_id: str
    passed: bool
    phantom_blocked: bool = False
    repair_success: bool = False
    retry_count: int = 0
    proof_present: bool = False
    regression_pass_rate: float = 0.0
    pattern_reuse: float = 0.0
    next_run_hit: float = 0.0
    metadata: Dict[str, Any] | None = None


def build_outcome_event(payload: OutcomePayload) -> Dict[str, Any]:
    md = payload.metadata or {}
    fail = not payload.passed
    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "task_id": str(payload.task_id),
        "phase": str(payload.phase),
        "decision_id": str(payload.decision_id),
        "skill_id": str(payload.skill_id),
        "pass": bool(payload.passed),
        "fail": bool(fail),
        "phantom_blocked": bool(payload.phantom_blocked),
        "regression_pass_rate": _safe_float(payload.regression_pass_rate),
        "self_heal_retry_count": int(max(0, payload.retry_count)),
        # Anti-hallucination signals
        "proof_present": bool(payload.proof_present),
        # Self-healing signals
        "repair_success": bool(payload.repair_success),
        "retry_count": int(max(0, payload.retry_count)),
        # Learning signals
        "pattern_reuse": _safe_float(payload.pattern_reuse),
        "next_run_hit": _safe_float(payload.next_run_hit),
        # Optional enrichments
        "status": str(md.get("status", "")),
        "audit_status": str(md.get("audit_status", "")),
        "source": str(md.get("source", "pipeline.crystallize")),
    }


def append_skill_outcome_event(project_root: Path, event: Dict[str, Any]) -> Path:
    output_path = project_root / EVENTS_REL_PATH
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False))
        handle.write("\n")
    return output_path
