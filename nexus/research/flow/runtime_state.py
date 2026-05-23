from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ParsedTuningKnobs:
    candidate_boost: int = 0
    max_rounds_boost: int = 0
    stage1_parallel_boost: int = 0
    baseline_fast_sec: float = 0.0
    skip_baseline_probe_for_hard: bool = False


def parse_tuning_knobs(payload: dict[str, Any] | None) -> ParsedTuningKnobs:
    raw = (payload or {}).get("knobs", {}) if isinstance(payload, dict) else {}
    if not isinstance(raw, dict):
        return ParsedTuningKnobs()
    try:
        candidate_boost = int(raw.get("candidate_boost", 0) or 0)
    except (TypeError, ValueError):
        candidate_boost = 0
    try:
        max_rounds_boost = int(raw.get("max_rounds_boost", 0) or 0)
    except (TypeError, ValueError):
        max_rounds_boost = 0
    try:
        stage1_parallel_boost = int(raw.get("stage1_parallel_boost", 0) or 0)
    except (TypeError, ValueError):
        stage1_parallel_boost = 0
    try:
        baseline_fast_sec = float(raw.get("baseline_fast_sec", 0.0) or 0.0)
    except (TypeError, ValueError):
        baseline_fast_sec = 0.0
    return ParsedTuningKnobs(
        candidate_boost=max(-2, min(2, candidate_boost)),
        max_rounds_boost=max(-2, min(2, max_rounds_boost)),
        stage1_parallel_boost=max(-2, min(2, stage1_parallel_boost)),
        baseline_fast_sec=max(0.0, baseline_fast_sec),
        skip_baseline_probe_for_hard=bool(raw.get("skip_baseline_probe_for_hard", False)),
    )


def read_belief_confidence_fast(repo_root: Path) -> float:
    path = (repo_root / ".nexus" / "belief_state.json").resolve()
    if not path.exists():
        return 1.0
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        raw = payload.get("confidence", payload.get("belief_confidence", 1.0))
        value = float(raw)
        return min(1.0, max(0.0, value))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return 1.0


def read_capability_tuning_fast(repo_root: Path) -> dict[str, Any]:
    override = str(os.environ.get("NEXUS_CAPABILITY_TUNING_FILE", "") or "").strip()
    path = Path(override).resolve() if override else (repo_root / ".nexus" / "config" / "capability_tuning.json").resolve()
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def read_phase_slo_summary_fast(repo_root: Path) -> dict[str, Any]:
    missing = {
        "phase_slo_pass": False,
        "global": {"required_done_ratio": 0.0},
        "status": "UNAVAILABLE",
        "reason": "phase_slo_summary_missing",
    }
    path = (repo_root / ".nexus" / "reports" / "learn" / "phase_slo_summary.json").resolve()
    if not path.exists():
        return missing
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("invalid_phase_slo_payload")
        payload.setdefault("phase_slo_pass", False)
        payload.setdefault("global", {"required_done_ratio": 0.0})
        payload.setdefault("status", "SUCCESS")
        payload.setdefault("reason", "")
        return payload
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return {**missing, "reason": "phase_slo_summary_invalid"}
