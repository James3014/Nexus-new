#!/usr/bin/env python3
# scripts/learning/cleanup_policy_memory.py

import argparse
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def cleanup_policy_memory(repo_root: Path, ttl_days: int = 90) -> Dict:
    """生產級 TTL 清理，串流讀寫避免 memory overflow。"""
    
    policy_path = repo_root / ".nexus/knowledge/policymemory.jsonl"
    
    if not policy_path.exists():
        logger.info("No policy memory found at %s", policy_path)
        return {"status": "no_data", "cleaned": 0, "kept": 0}
    
    original_size = policy_path.stat().st_size
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=ttl_days)
    temp_path = policy_path.with_suffix(".tmp")
    
    kept, cleaned = 0, 0
    
    try:
        with open(policy_path, "r", encoding="utf-8") as infile, \
             open(temp_path, "w", encoding="utf-8") as outfile:
            for line_num, line in enumerate(infile, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    # 解析時間戳 (相容 Z 或 +00:00)
                    ts_str = record.get("timestamp", "").replace("Z", "+00:00")
                    ts = datetime.fromisoformat(ts_str)
                    
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    
                    if ts > cutoff:
                        outfile.write(line + "\n")
                        kept += 1
                    else:
                        cleaned += 1
                        
                except (json.JSONDecodeError, KeyError, ValueError) as e:
                    logger.warning("Line %d corrupted, skipping: %s", line_num, e)
                    cleaned += 1
        
        # 原子替換
        temp_path.replace(policy_path)
        
        final_size = policy_path.stat().st_size
        logger.info("Cleanup complete: kept=%d, cleaned=%d, size=%.1fMB → %.1fMB",
                   kept, cleaned, original_size/(1024*1024), final_size/(1024*1024))
        
        return {
            "status": "success",
            "ttl_days": ttl_days,
            "cutoff": cutoff.isoformat(),
            "original_size_mb": round(original_size / (1024*1024), 2),
            "final_size_mb": round(final_size / (1024*1024), 2),
            "kept": kept,
            "cleaned": cleaned,
            "compression_ratio": round(final_size / max(1, original_size), 4),
        }
        
    except Exception as e:
        logger.error("Cleanup failed: %s", e)
        if temp_path.exists():
            temp_path.unlink()
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("repo_root", nargs="?", default=".", type=Path)
    parser.add_argument("--ttl-days", default=90, type=int)
    args = parser.parse_args()
    
    result = cleanup_policy_memory(args.repo_root, args.ttl_days)
    print(json.dumps(result, indent=2, ensure_ascii=False))
