# scripts/learning/audit_production_chain.py

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections import defaultdict, Counter
from typing import Dict, Any


def audit_swarm_decisions(repo_root: Path, days: int = 7) -> Dict[str, Any]:
    """🛡️ 審計 policymemory.jsonl 決策分佈與治理有效性"""
    
    policy_path = repo_root / ".nexus" / "knowledge" / "policymemory.jsonl"
    if not policy_path.exists():
        return {"status": "no_policy_memory", "path": str(policy_path)}
    
    decisions_by_phase = defaultdict(list)
    decisions_by_route = Counter()
    block_count = 0
    total_decisions = 0
    
    # 設置審計窗口
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    
    try:
        with open(policy_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                record = json.loads(line.strip())
                
                # 解析時間戳 (相容 Z 或 +00:00)
                ts_str = record["timestamp"].replace("Z", "+00:00")
                ts = datetime.fromisoformat(ts_str)
                
                # 如果時間戳不帶時區，強制設為 UTC
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                
                if ts > cutoff:
                    phase = record.get("phase", "unknown")
                    decisions_by_phase[phase].append(record)
                    decisions_by_route[record.get("route_id", "unknown")] += 1
                    
                    if record.get("decision") == "block":
                        block_count += 1
                    total_decisions += 1
    except Exception as e:
        return {"status": "error", "message": f"Failed to parse policy memory: {e}"}
    
    block_rate = block_count / max(1, total_decisions)
    
    return {
        "status": "success",
        "audit_period_days": days,
        "total_decisions": total_decisions,
        "block_count": block_count,
        "block_rate": round(block_rate, 4),
        "decisions_by_phase": dict(decisions_by_phase),
        "top_routes": decisions_by_route.most_common(10),
        "recent_policy_memory_path": str(policy_path),
    }


if __name__ == "__main__":
    import sys
    import click
    
    @click.command()
    @click.argument("workspace_root", type=click.Path(exists=True), default=".")
    @click.option("--days", default=7, type=int, help="審計天數範圍")
    def main(workspace_root: str, days: int):
        repo_root = Path(workspace_root)
        audit = audit_swarm_decisions(repo_root, days)
        print(json.dumps(audit, indent=2, ensure_ascii=False))
    
    if len(sys.argv) > 1 and sys.argv[1] == "main": # 內部調用支援
        pass
    else:
        main()
