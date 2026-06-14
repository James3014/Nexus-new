"""
🛡️ Nexus Health Analyzer: 生產健康指標分析與預警 (P2-C)
負責計算各 Phase 的成功率、幻覺率 (Phantom Rate) 與模式重用率 (Pattern Reuse)。
"""

from pathlib import Path
from typing import Dict, List, Optional
import json
from datetime import datetime, timezone, timedelta

from nexus.services.memory_indexer import connect_memory_db, TABLE_NAME

def compute_phase_health(repo_root: Path, phase: str, window_days: int = 90) -> Dict:
    """
    計算單一 phase 的健康指標。
    指標對齊 v22 規範：
    - autorepair_success_rate: repair_success=True 比率
    - phantom_fp_rate: phantom_blocked=True 比率
    - health_score: 0.8 * Success + 0.2 * Pattern Reuse
    """
    try:
        import pandas as pd
        db = connect_memory_db(repo_root)
        table = db.open_table(TABLE_NAME)
        
        # 建立時間過濾
        cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
        
        # 抓取該 Phase 的所有 outcome events
        # 注意：LanceDB query 需要正確過濾日期 (created_at_utc 比對)
        hits = table.search([]).where(
            f"record_type = 'outcome_event' AND phase = '{phase}'"
        ).to_pandas()
        
        if hits.empty:
            return {
                "status": "insufficient_data",
                "phase": phase,
                "message": f"No outcome events found for phase {phase} in the last {window_days} days."
            }
        
        # 補足時間過濾 (Panda side since LanceDB SQL filter for ISO strings might be touchy)
        hits['created_dt'] = pd.to_datetime(hits['created_at_utc'], utc=True)
        hits = hits[hits['created_dt'] >= cutoff]
        
        if hits.empty:
            return {"status": "no_recent_data", "phase": phase}

        # 解析 Payload
        payloads = [json.loads(p) for p in hits["payload_json"]]
        df = pd.DataFrame(payloads)
        
        total = len(df)
        # repair_success 預計為 bool
        success_count = df[df["repair_success"] == True].shape[0] if "repair_success" in df.columns else 0
        # phantom_blocked 預計為 bool
        phantom_count = df[df["phantom_blocked"] == True].shape[0] if "phantom_blocked" in df.columns else 0
        
        success_rate = success_count / total if total > 0 else 0.0
        phantom_rate = phantom_count / total if total > 0 else 0.0
        # pattern_reuse 平均 (score_hint 欄位即為 pattern_reuse/100)
        avg_pattern_reuse = hits["score_hint"].mean() if total > 0 else 0.0
        
        # v22 Health Score 權重：0.8 Success + 0.2 Pattern Reuse
        health_score = (success_rate * 0.8) + (avg_pattern_reuse * 0.2)
        
        return {
            "status": "healthy" if health_score > 0.7 else "degraded",
            "phase": phase,
            "window_days": window_days,
            "metrics": {
                "total_events": total,
                "autorepair_success_rate": round(success_rate, 4),
                "phantom_fp_rate": round(phantom_rate, 4),
                "pattern_reuse_rate": round(avg_pattern_reuse, 4),
                "health_score": round(health_score, 4)
            },
            "timestamp_utc": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        return {"status": "error", "message": str(e), "phase": phase}

def compute_overall_health(repo_root: Path) -> Dict:
    """全階段健康總覽"""
    phases = ["P", "X", "D", "R", "A", "C"]
    overall = {}
    for p in phases:
        overall[p] = compute_phase_health(repo_root, p)
    
    return {
        "status": "ok",
        "overall": overall,
        "summary": {
            "critical_phases": [p for p, res in overall.items() if res.get("status") == "degraded"],
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    }
