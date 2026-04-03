#!/usr/bin/env python3
# desk/api_swarm_metrics.py

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

# PYTHONPATH 處理
import sys
import os
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from scripts.learning.audit_production_chain import audit_swarm_decisions
except ImportError:
    # 支援手動執行時的目錄層級
    sys.path.append(os.getcwd())
    from scripts.learning.audit_production_chain import audit_swarm_decisions

def get_swarm_metrics(repo_root: Path, window_days: int = 7):
    """聚合 Swarm 審計、權重與存儲指標。"""
    
    # 1. 審計數據 (Days=7)
    audit = audit_swarm_decisions(repo_root, window_days)
    
    # 2. 權重狀態
    weights_path = repo_root / ".nexus/swarm/weights.json"
    weights = {}
    if weights_path.exists():
        try:
            with open(weights_path, "r", encoding="utf-8") as f:
                weights = json.load(f)
        except Exception:
            pass
            
    # 3. 政策記憶統計
    policy_path = repo_root / ".nexus/knowledge/policymemory.jsonl"
    policy_size_mb = 0.0
    if policy_path.exists():
        policy_size_mb = round(policy_path.stat().st_size / (1024 * 1024), 2)
        
    # 4. 路由統計轉化為 Top Routes (按 usage_count 排序)
    route_usage = []
    for route, info in weights.items():
        route_usage.append({
            "route": route,
            "usage": info.get("usage_count", 0)
        })
    route_usage.sort(key=lambda x: x["usage"], reverse=True)
    
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "block_rate": audit.get("block_rate", 0.0),
        "route_count": len(weights),
        "policy_size_mb": policy_size_mb,
        "total_decisions": audit.get("total_decisions", 0),
        "top_routes": route_usage,
        "weights": weights,
        "status": "success"
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("repo_root", nargs="?", default=".", type=Path)
    parser.add_argument("--window-days", default=7, type=int)
    args = parser.parse_args()
    
    metrics = get_swarm_metrics(args.repo_root, args.window_days)
    print(json.dumps(metrics, indent=2, ensure_ascii=False))
