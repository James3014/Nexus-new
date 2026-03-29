from __future__ import annotations

from typing import Any, Dict, List


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def build_research_pack(
    *,
    task: str,
    mode: str,
    source: str,
    reason: str,
    hypotheses: List[Dict[str, Any]] | None = None,
    experiments: List[Dict[str, Any]] | None = None,
    winner: Dict[str, Any] | None = None,
    eliminated: List[str] | None = None,
    rounds: int = 0,
    time_sec: float = 0.0,
    status: str = "SUCCESS",
    findings: List[str] | None = None,
    raw: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    hypotheses = hypotheses or []
    experiments = experiments or []
    winner = winner or {}
    eliminated = eliminated or []
    findings = findings or []
    raw = raw or {}

    return {
        "schema_version": "research_pack.v1",
        "task": task,
        "mode": mode,
        "source": source,
        "status": status,
        "reason": reason,
        "hypotheses": hypotheses,
        "experiments": experiments,
        "winner": winner,
        "eliminated": eliminated,
        "budget_used": {
            "rounds": int(rounds),
            "time_sec": _as_float(time_sec, 0.0),
        },
        # Backward-compatible fields for existing consumers.
        "findings": findings,
        "token_fallback_est": int(raw.get("tokens_used", 0) or 0),
        "token_capture_status": str(raw.get("token_capture_status", "n/a")),
        "raw": raw,
    }

