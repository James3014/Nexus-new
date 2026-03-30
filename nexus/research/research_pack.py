from __future__ import annotations

from typing import Any, Dict, List
import datetime


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


from dataclasses import dataclass, field

@dataclass
class ResearchContext:
    """R1: build_research_pack 的參數物件。"""
    task: str
    mode: str
    source: str
    reason: str
    hypotheses: List[Dict[str, Any]] = field(default_factory=list)
    experiments: List[Dict[str, Any]] = field(default_factory=list)
    winner: Dict[str, Any] = field(default_factory=dict)
    eliminated: List[str] = field(default_factory=list)
    rounds: int = 0
    time_sec: float = 0.0
    status: str = "SUCCESS"
    findings: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)


def build_research_pack(ctx: ResearchContext) -> Dict[str, Any]:
    hypotheses = ctx.hypotheses or []
    experiments = ctx.experiments or []
    winner = ctx.winner or {}
    eliminated = ctx.eliminated or []
    findings = ctx.findings or []
    raw = ctx.raw or {}

    return {
        "schema_version": "research_pack.v1",
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "task": ctx.task,
        "mode": ctx.mode,
        "source": ctx.source,
        "status": ctx.status,
        "reason": ctx.reason,
        "hypotheses": hypotheses,
        "experiments": experiments,
        "winner": winner,
        "eliminated": eliminated,
        "budget_used": {
            "rounds": int(ctx.rounds),
            "time_sec": _as_float(ctx.time_sec, 0.0),
        },
        # Backward-compatible fields for existing consumers.
        "findings": findings,
        "token_fallback_est": int(raw.get("tokens_used", 0) or 0),
        "token_capture_status": str(raw.get("token_capture_status", "n/a")),
        "raw": raw,
    }

