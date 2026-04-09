import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from nexus.engine.autonomic_router import AutonomicRouter

logger = logging.getLogger(__name__)

class RouterNASTuner:
    """
    🧠 Nexus NAS Tuner (v24.5)
    職責: 根據歷史任務成敗自動微調 AutonomicRouter 的決策閾值。
    演算法: Heuristic Gradient Step (±5% limit)
    """
    def __init__(self, project_root: str = ".", memory_service=None):
        self.project_root = Path(project_root).resolve()
        self.memory = memory_service
        self.router = AutonomicRouter(project_root=str(self.project_root), memory_service=memory_service)

    def tune_step(self, recent_history: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        執行一次微調步進。
        recent_history 格式: [{"mode": "standard", "est_tokens": 7500, "pass": False}, ...]
        """
        config = self.router.config.copy()
        current_token_threshold = config.get("token_threshold", 8000)
        
        # 1. 分析 Token 閾值相關失敗
        # 找出那些接近閾值 (80% ~ 100%) 卻失敗的 standard 任務
        failure_near_threshold = [
            h for h in recent_history 
            if h.get("mode") == "standard" 
            and not h.get("pass", True) 
            and h.get("est_tokens", 0) > (current_token_threshold * 0.8)
        ]
        
        # 找出那些接近閾值且成功的 standard 任務
        success_near_threshold = [
            h for h in recent_history 
            if h.get("mode") == "standard" 
            and h.get("pass", False) 
            and h.get("est_tokens", 0) > (current_token_threshold * 0.8)
        ]

        adjustment = 0
        
        # 如果失敗率過高 (例如 > 20% 且至少有 2 筆失敗) -> 閾值降級 (安全性優先)
        if len(failure_near_threshold) >= 2:
            failure_rate = len(failure_near_threshold) / (len(failure_near_threshold) + len(success_near_threshold))
            if failure_rate > 0.2:
                adjustment = -0.05 # 降低 5%
                logger.info(f"📉 [NAS] High failure rate ({failure_rate:.0%}) detected near threshold. Reducing token_threshold.")

        # 如果幾乎沒失敗且樣本足夠 -> 閾值升級 (成本優化)
        elif len(success_near_threshold) >= 5 and len(failure_near_threshold) == 0:
            adjustment = 0.05 # 提高 5%
            logger.info(f"📈 [NAS] High success rate detected. Raising token_threshold for cost optimization.")

        if adjustment != 0:
            new_threshold = int(current_token_threshold * (1 + adjustment))
            # 物理限制: 不低於 2000, 不高於 50000
            new_threshold = max(2000, min(50000, new_threshold))
            config["token_threshold"] = new_threshold
            self.router._save_config(config)
            return {"updated": True, "old": current_token_threshold, "new": new_threshold}
        
        return {"updated": False}

    def auto_tune_from_log(self, limit: int = 50):
        """從 skill_outcome_events.jsonl 自動提取數據並調優"""
        log_path = self.project_root / ".nexus" / "metrics" / "skill_outcome_events.jsonl"
        if not log_path.exists():
            return {"updated": False, "reason": "No log file found"}
            
        history = []
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                # 讀取最後 N 行
                lines = f.readlines()[-limit:]
                for line in lines:
                    data = json.loads(line)
                    meta = data.get("metadata", {})
                    # 提取路由決策相關資訊
                    history.append({
                        "mode": meta.get("autonomic_route", "standard"),
                        "est_tokens": meta.get("est_tokens", 0), # 這裡要確保 metadata 裡有這欄
                        "pass": data.get("pass", False)
                    })
        except Exception as e:
            logger.error(f"❌ [NAS] History load failed: {e}")
            return {"updated": False, "reason": str(e)}

        if not history:
            return {"updated": False, "reason": "No valid history records found"}
            
        return self.tune_step(history)
