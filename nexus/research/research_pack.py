from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple

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
    role: str = "general"
    hypotheses: List[Dict[str, Any]] = field(default_factory=list)
    experiments: List[Dict[str, Any]] = field(default_factory=list)
    winner: Dict[str, Any] = field(default_factory=dict)
    eliminated: List[str] = field(default_factory=list)
    rounds: int = 0
    time_sec: float = 0.0
    status: str = "SUCCESS"
    findings: List[str] = field(default_factory=list)
    verified_claims: List[Dict[str, Any]] = field(default_factory=list)
    rejected_claims: List[Dict[str, Any]] = field(default_factory=list)
    retrieval_refs: List[str] = field(default_factory=list)
    risk_flags: List[str] = field(default_factory=list)
    recommended_capabilities: List[str] = field(default_factory=list)
    blocked_assumptions: List[str] = field(default_factory=list)
    next_action_hint: str = ""
    confidence: float = 0.0
    raw: Dict[str, Any] = field(default_factory=dict)


def build_research_pack(ctx: ResearchContext) -> Dict[str, Any]:
    hypotheses = ctx.hypotheses or []
    experiments = ctx.experiments or []
    winner = ctx.winner or {}
    eliminated = ctx.eliminated or []
    findings = ctx.findings or []
    verified_claims = ctx.verified_claims or []
    rejected_claims = ctx.rejected_claims or []
    retrieval_refs = ctx.retrieval_refs or []
    risk_flags = ctx.risk_flags or []
    recommended_capabilities = ctx.recommended_capabilities or []
    blocked_assumptions = ctx.blocked_assumptions or []
    raw = ctx.raw or {}

    context_v2 = {
        "schema_version": "research_context.v2",
        "role": ctx.role or "general",
        "verified_claims": verified_claims,
        "rejected_claims": rejected_claims,
        "retrieval_refs": retrieval_refs,
        "risk_flags": risk_flags,
        "recommended_capabilities": recommended_capabilities,
        "blocked_assumptions": blocked_assumptions,
        "next_action_hint": str(ctx.next_action_hint or ""),
        "confidence": max(0.0, min(1.0, _as_float(ctx.confidence, 0.0))),
    }

    return {
        "schema_version": "research_pack.v1",
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "task": ctx.task,
        "mode": ctx.mode,
        "source": ctx.source,
        "status": ctx.status,
        "reason": ctx.reason,
        "role": context_v2["role"],
        "hypotheses": hypotheses,
        "experiments": experiments,
        "winner": winner,
        "eliminated": eliminated,
        "budget_used": {
            "rounds": int(ctx.rounds),
            "time_sec": _as_float(ctx.time_sec, 0.0),
        },
        "verified_claims": verified_claims,
        "rejected_claims": rejected_claims,
        "retrieval_refs": retrieval_refs,
        "risk_flags": risk_flags,
        "recommended_capabilities": recommended_capabilities,
        "blocked_assumptions": blocked_assumptions,
        "next_action_hint": context_v2["next_action_hint"],
        "confidence": context_v2["confidence"],
        "context_v2": context_v2,
        # Backward-compatible fields for existing consumers.
        "findings": findings,
        "token_fallback_est": int(raw.get("tokens_used", 0) or 0),
        "token_capture_status": str(raw.get("token_capture_status", "n/a")),
        "raw": raw,
    }
