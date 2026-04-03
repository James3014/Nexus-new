# nexus/services/self_heal_selector.py

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Any

from nexus.services.swarm_router import RouteCandidate, select_best_route
from nexus.services.policy_gate import apply_policy_gate
from nexus.services.health_analyzer import compute_phase_health


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
    
    # 2. Swarm 基礎路由評分
    route_decision = select_best_route(candidates)
    
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
            "selected_route": "legacy-core-router",
            "backend_used": "legacy-fallback",
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
    """載入 self-heal 專用修復候選。"""
    from scripts.learning.compute_route_weights import load_mock_candidates
    # 未來將升級為從 .nexus/inventory 加載真正的 Agents
    return load_mock_candidates(repo_root, phase)[:max_candidates]
