# nexus/services/swarm_router.py

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional


@dataclass
class RouteCandidate:
    route_id: str
    provider: str
    armor_id: str
    phase: str
    base_weight: float = 0.5
    success_rate: float = 0.5
    pattern_reuse: float = 0.0
    next_run_hit: float = 0.0
    phantom_fp_rate: float = 0.0
    regression_pass_rate: float = 1.0
    recent_uses: int = 0
    available: bool = True
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        """P4: 自動載入由 Autotune 產出的路由權重 (base_weight)。"""
        import json
        from pathlib import Path
        weights_path = Path(".nexus/swarm/weights.json")
        if weights_path.exists():
            try:
                with open(weights_path, "r", encoding="utf-8") as f:
                    tuned_weights = json.load(f)
                
                # 比對 route_id
                if self.route_id in tuned_weights:
                    new_weight = tuned_weights[self.route_id].get("base_weight")
                    if new_weight is not None:
                        self.base_weight = float(new_weight)
            except Exception:
                # 靜默失敗以維持系統穩定 (fail-closed)
                pass


@dataclass
class RouteDecision:
    selected_route: str
    score: float
    backend_used: str
    explanation: Dict[str, Any]
    ranked_candidates: List[Dict[str, Any]]


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def score_route(candidate: RouteCandidate) -> Dict[str, Any]:
    """
    🛡️ Swarm Route Scoring Algorithm (v22 Spec)
    Formula: 0.35*base + 0.25*success + 0.15*reuse + 0.10*nextrun + 0.10*regression - 0.15*phantom
    """
    if not candidate.available:
        return {
            "route_id": candidate.route_id,
            "score": -1.0,
            "explanation": {"reason": "unavailable"},
        }

    success = _clamp(candidate.success_rate)
    reuse = _clamp(candidate.pattern_reuse)
    next_hit = _clamp(candidate.next_run_hit)
    phantom_penalty = _clamp(candidate.phantom_fp_rate)
    regression = _clamp(candidate.regression_pass_rate)
    base = _clamp(candidate.base_weight)

    score = (
        0.35 * base +
        0.25 * success +
        0.15 * reuse +
        0.10 * next_hit +
        0.10 * regression -
        0.15 * phantom_penalty
    )

    return {
        "route_id": candidate.route_id,
        "score": round(score, 4),
        "explanation": {
            "base_weight": base,
            "success_rate": success,
            "pattern_reuse": reuse,
            "next_run_hit": next_hit,
            "regression_pass_rate": regression,
            "phantom_fp_penalty": phantom_penalty,
            "formula": "0.35*base + 0.25*success + 0.15*reuse + 0.10*nextrun + 0.10*regression - 0.15*phantom",
        },
        "candidate": asdict(candidate),
    }


def select_best_route(
    candidates: List[RouteCandidate],
    *,
    fallback_route_id: str = "no-route-available",
) -> RouteDecision:
    """
    🏆 最佳路徑選擇：無可用候選時 fail-closed，不偽造 legacy route。
    """
    if not candidates:
        return RouteDecision(
            selected_route=fallback_route_id,
            score=0.0,
            backend_used="fail-closed",
            explanation={"reason": "no_candidates"},
            ranked_candidates=[],
        )

    ranked = [score_route(c) for c in candidates]
    ranked.sort(key=lambda x: x["score"], reverse=True)

    best = ranked[0]
    if best["score"] < 0:
        return RouteDecision(
            selected_route=fallback_route_id,
            score=0.0,
            backend_used="fail-closed",
            explanation={"reason": "all_candidates_unavailable"},
            ranked_candidates=ranked,
        )

    return RouteDecision(
        selected_route=best["route_id"],
        score=best["score"],
        backend_used="swarm",
        explanation=best["explanation"],
        ranked_candidates=ranked,
    )
