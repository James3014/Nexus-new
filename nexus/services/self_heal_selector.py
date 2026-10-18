# nexus/services/self_heal_selector.py

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Any
import logging

from nexus.services.swarm_router import RouteCandidate, select_best_route
from nexus.services.policy_gate import apply_policy_gate
from nexus.services.health_analyzer import compute_phase_health

logger = logging.getLogger(__name__)

SELF_HEAL_CANDIDATE_SOURCE_MISSING = "self_heal_candidate_source_missing"


def select_self_heal_route(
    repo_root: Path,
    phase: str,
    diagnosis: Dict[str, Any],
    *,
    max_candidates: int = 8,
) -> Dict[str, Any]:
    """
    🛡️ Self-heal 專用路由選擇：結合 Swarm Router 與 Policy Gate。
    """
    
    # 1. 載入修復候選 (目前對接 Day 1 Loader)
    candidates = load_self_heal_candidates(repo_root, phase, max_candidates)
    if not candidates:
        return {
            "selected_route": "no-route-available",
            "backend_used": "fail-closed",
            "reason": SELF_HEAL_CANDIDATE_SOURCE_MISSING,
            "gated_score": 0.0,
            "signals": [],
            "health_metrics": {},
        }

    # 2. Swarm 基礎路由評分
    route_decision = select_best_route(candidates)
    if route_decision.backend_used == "fail-closed":
        return {
            "selected_route": route_decision.selected_route,
            "backend_used": "fail-closed",
            "reason": route_decision.explanation.get("reason", "route_unavailable"),
            "gated_score": route_decision.score,
            "signals": [],
            "health_metrics": {},
        }
    
    # 3. 獲取當前 Phase 健康指標
    health = compute_phase_health(repo_root, phase)
    # 提取 metrics 元組 (相容 P2-C/P3 格式)
    actual_metrics = health.get("metrics", health)
    
    # 4. 執行 Policy Gate 分層治理決策
    gate_decision = apply_policy_gate(
        route_id=route_decision.selected_route,
        original_score=route_decision.score,
        phase=phase,
        health_metrics=actual_metrics,
        repo_root=repo_root,
    )
    
    # 5. 生成 Self-heal 整合決策
    if gate_decision.decision == "block":
        return {
            "selected_route": "policy-blocked",
            "backend_used": "fail-closed",
            "reason": "policy-blocked",
            "gated_score": gate_decision.gated_score,
            "signals": [s.__dict__ for s in gate_decision.signals],
            "health_metrics": health,
        }
    
    return {
        "selected_route": gate_decision.route_id,
        "backend_used": "swarm-gated",
        "gated_score": gate_decision.gated_score,
        "signals": [s.__dict__ for s in gate_decision.signals],
        "health_metrics": health,
    }


def load_self_heal_candidates(
    repo_root: Path,
    phase: str,
    max_candidates: int,
) -> List[RouteCandidate]:
    """載入 self-heal 專用修復候選。

    There is no production candidate source. The old code imported the
    nonexistent ``nexus.core.learning`` route-weight loader and, on the
    ImportError, silently returned a hard-coded rust-v16 route, so every
    repair looked swarm-routed (#2637). Return no candidates instead and log
    it; ``select_self_heal_route`` then fails closed with
    ``SELF_HEAL_CANDIDATE_SOURCE_MISSING``.
    """
    logger.warning(
        "self-heal candidate source missing (phase=%s); routing fails closed (#2637)",
        phase,
    )
    return []
