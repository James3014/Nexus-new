# scripts/learning/compute_route_weights.py

from __future__ import annotations

import json
from pathlib import Path
from typing import List

from nexus.services.swarm_router import RouteCandidate, select_best_route
from nexus.services.policy_gate import apply_policy_gate
from nexus.services.health_analyzer import compute_phase_health


def load_mock_candidates(repo_root: Path, phase: str) -> List[RouteCandidate]:
    """載入模擬路由候選 (MOCK)。"""
    return [
        RouteCandidate(
            route_id="rust-v16",
            provider="rust",
            armor_id="rust-v16",
            phase=phase,
            base_weight=0.72,
            success_rate=0.91,
            pattern_reuse=0.84,
            next_run_hit=0.79,
            phantom_fp_rate=0.02,
            regression_pass_rate=0.97,
        ),
        RouteCandidate(
            route_id="python-v17",
            provider="python",
            armor_id="python-v17",
            phase=phase,
            base_weight=0.69,
            success_rate=0.86,
            pattern_reuse=0.71,
            next_run_hit=0.68,
            phantom_fp_rate=0.05,
            regression_pass_rate=0.93,
        ),
    ]


def main(workspace_root: str, phase: str = "R") -> int:
    repo_root = Path(workspace_root)
    
    # 1. 執行基礎路由評分
    candidates = load_mock_candidates(repo_root, phase)
    route_decision = select_best_route(candidates)
    
    # 2. 執行 Policy Gating (對應 P3 Day 2)
    # 這裡我們調用真正的 health_analyzer (P2-C)
    health_data = compute_phase_health(repo_root, phase)
    # 如果有 metrics 子字典則提取，否則用原字典 (相容模式)
    actual_metrics = health_data.get("metrics", health_data)
    
    gate_decision = apply_policy_gate(
        route_id=route_decision.selected_route,
        original_score=route_decision.score,
        phase=phase,
        health_metrics=actual_metrics,
        repo_root=repo_root,
    )
    
    print(json.dumps({
        "phase": phase,
        "route_decision": {
            "selected_route": route_decision.selected_route,
            "original_score": route_decision.score,
            "backend_used": route_decision.backend_used,
        },
        "gate_decision": {
            "gated_score": gate_decision.gated_score,
            "decision": gate_decision.decision.value,
            "signals": [s.__dict__ for s in gate_decision.signals],
            "policy_version": gate_decision.policy_version,
        },
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main(".", sys.argv[1] if len(sys.argv) > 1 else "R"))
