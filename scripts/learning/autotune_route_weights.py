#!/usr/bin/env python3
# scripts/learning/autotune_route_weights.py

import argparse
import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

from scripts.learning.audit_production_chain import audit_swarm_decisions

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def autotune_from_history(repo_root: Path, window_days: int = 7) -> Dict:
    """基於歷史表現動態調優 route base_weight。"""
    
    audit = audit_swarm_decisions(repo_root, window_days)
    if audit.get("status") != "success":
        logger.warning("Audit failed, skipping autotune: %s", audit.get("message", "unknown"))
        return {"status": "skipped", "reason": audit.get("message", "no_policy_memory")}

    route_stats = defaultdict(lambda: {"usage": 0, "blocked": 0, "healthy": 0})
    
    # 統計各 route 表現
    for phase_name, decisions in audit.get("decisions_by_phase", {}).items():
        for record in decisions:
            route = record.get("route_id", "unknown")
            route_stats[route]["usage"] += 1
            
            if record.get("decision") == "block":
                route_stats[route]["blocked"] += 1
            # 判斷健康度：gated_score > 0.5 或原有 health_metrics
            gated_score = record.get("gated_score", 0.0)
            health = record.get("health_metrics", {}).get("health_score", 0.0)
            if gated_score > 0.5 or health > 0.7:
                route_stats[route]["healthy"] += 1
    
    weights = {}
    now_str = datetime.now(timezone.utc).isoformat()
    
    for route, stats in route_stats.items():
        total = stats["usage"]
        if total == 0:
            continue
            
        # 成功率與阻斷率
        success_rate = stats["healthy"] / total
        block_rate = stats["blocked"] / total
        
        # 動態 base_weight: 0.5 基準 + 使用率加成 + 成功加成 - 阻斷懲罰
        # 使用率加成 (最高 0.2)，鼓勵經過多次驗證的路徑
        usage_bias = min(0.2, total / 1000)
        # 成功加成 (最高 0.2)
        success_bonus = 0.2 * success_rate
        # 阻斷懲罰 (最高 0.3)
        block_penalty = 0.3 * block_rate
        
        new_base = 0.5 + usage_bias + success_bonus - block_penalty
        new_base = round(max(0.1, min(0.9, new_base)), 4)
        
        weights[route] = {
            "base_weight": new_base,
            "usage_count": total,
            "success_rate": round(success_rate, 4),
            "block_rate": round(block_rate, 4),
            "updated_at": now_str,
            "window_days": window_days,
        }
    
    # 存檔
    weights_path = repo_root / ".nexus/swarm/weights.json"
    weights_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(weights_path, "w", encoding="utf-8") as f:
        json.dump(weights, f, indent=2, ensure_ascii=False)
    
    logger.info("Autotuned %d routes -> %s", len(weights), weights_path)
    return weights


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("repo_root", nargs="?", default=".", type=Path)
    parser.add_argument("--window-days", default=7, type=int)
    args = parser.parse_args()
    
    weights = autotune_from_history(args.repo_root, args.window_days)
    print(json.dumps(weights, indent=2, ensure_ascii=False))
