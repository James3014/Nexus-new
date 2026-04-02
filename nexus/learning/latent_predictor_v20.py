from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import logging
import json
import numpy as np
from nexus.core.vector_rag import VectorRAG

logger = logging.getLogger(__name__)

class LatentPredictorV20:
    """
    🧬 Nexus v20 JEPA Latent Predictor
    職責: 在任務執行前，基於隱空間相似性預測 ROI 與風險。
    實現「零 Token 預演」。
    """
    
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        # 整合現有的 VectorRAG 用於隱空間檢索
        self.rag = VectorRAG(db_path=".nexus/vector_db")
        self.history_limit = 5

    def forecast_roi(self, task_desc: str) -> Dict[str, Any]:
        """
        🚀 零 Token 預演 (Zero-token Forecasting)
        輸入任務描述，預測 Tokens 消耗與延遲。
        """
        logger.info("📡 [JEPA:v20] Forecasting ROI for task: %s", task_desc[:50])
        
        # 1. 執行隱空間相似性檢索 (LanceDB)
        # 物理真值：尋找歷史相似任務
        similar_missions = self.rag.query(task_desc, k=self.history_limit)
        
        if not similar_missions:
            # 沒歷史數據時執行「冷啟動預測 (Cold-start Heuristic)」
            return {
                "confidence": "LOW",
                "est_tokens": 1500,
                "est_latency_sec": 180,
                "roi_score": 0.5,
                "evidence": "cold_start_heuristic"
            }
            
        # 2. 數據聚合 (Aggregating outcomes)
        tokens_list = []
        latency_list = []
        for miss in similar_missions:
            meta = miss.get("metadata", {})
            tokens_list.append(meta.get("actual_tokens", 1000))
            latency_list.append(meta.get("actual_latency", 60))
            
        avg_tokens = int(np.mean(tokens_list)) if tokens_list else 1500
        avg_latency = int(np.mean(latency_list)) if latency_list else 180
        
        # 3. 計算 ROI 分數 (ROI < 0.5 將觸發 Auto-Reject)
        roi_score = 1.0 - (avg_tokens / 10000.0)
        
        return {
            "confidence": "HIGH" if len(similar_missions) >= 3 else "MEDIUM",
            "est_tokens": avg_tokens,
            "est_latency_sec": avg_latency,
            "roi_score": max(0.1, min(1.0, roi_score)),
            "matches": len(similar_missions)
        }

    def predict_risk(self, task_desc: str) -> Dict[str, Any]:
        """
        🛡️ 風險感應預先防禦 (Predictive Risk Shield)
        檢測任務是否包含已知的衝突模式。
        """
        risky_patterns = {
            "subprocess": "HIGH (AST Gate Potential)",
            "rm -rf": "CRITICAL (Safety Block)",
            "hardcode": "MEDIUM (Debt)",
            "NexusState": "HIGH (Core Geometry Risk)"
        }
        
        detected_risks = []
        reject_prob = 0.05
        
        for pattern, risk_level in risky_patterns.items():
            if pattern.lower() in task_desc.lower():
                detected_risks.append({"type": pattern, "level": risk_level})
                reject_prob += 0.4
                
        return {
            "risks": detected_risks,
            "reject_prob": min(0.99, reject_prob),
            "status": "CAUTION" if detected_risks else "CLEAR"
        }

def get_latent_forecaster(root: str = ".") -> LatentPredictorV20:
    return LatentPredictorV20(Path(root).resolve())
