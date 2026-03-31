import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from nexus.learning.latent_predictor_v20 import LatentPredictorV20

logger = logging.getLogger(__name__)

class SelfHealingSelector:
    """
    🛡️ Nexus v20 Adaptive Self-Healing (ASH) Selector
    職責: 當蜂群節點失敗時，預測並選擇最優自癒策略。
    實現「預演式自癒」。
    """
    
    def __init__(self, predictor: LatentPredictorV20):
        self.predictor = predictor
        self.strategies = [
            {"id": "FIX_DIRECTLY", "success_base": 0.4, "description": "嘗試直接修復錯誤"},
            {"id": "RESEARCH_FIRST", "success_base": 0.7, "description": "優先執行 SOTA 研究尋找解法"},
            {"id": "REPLAN_SWARM", "success_base": 0.8, "description": "重構子任務圖並重新並行"}
        ]

    def rank_strategies(self, task_desc: str, failure_context: str) -> List[Dict[str, Any]]:
        """
        🚀 戰略預演：對各修復選項進行成功率排序。
        """
        logger.info("📡 [ASH:v20] Ranking self-healing strategies for failure: %s", task_desc[:50])
        
        ranked = []
        for strat in self.strategies:
            # 物理對位：利用預演器預測風險與 ROI
            # 這裡模擬預演器對策略的 latent 擬合
            prediction = self.predictor.forecast_roi(f"Self-heal via {strat['id']}: {task_desc}")
            
            # 計算合成成功率 (Success Prob)
            success_prob = strat['success_base'] * prediction["roi_score"]
            
            # 風險懲罰
            risk = self.predictor.predict_risk(failure_context)
            if risk["status"] == "CAUTION":
                success_prob *= (1.0 - risk["reject_prob"])
                
            ranked.append({
                "strategy": strat["id"],
                "success_prob": round(success_prob, 2),
                "prediction": prediction,
                "risk_status": risk["status"]
            })
            
        # 按成功率降序排列
        return sorted(ranked, key=lambda x: x["success_prob"], reverse=True)

    def trigger_ash(self, node_id: str, task_desc: str, failure_context: str) -> Dict[str, Any]:
        """
        具現化自癒決策。
        """
        logger.warning("🚨 [ASH:v20] Node [%s] failed. Triggering adaptive repair...", node_id)
        
        candidates = self.rank_strategies(task_desc, failure_context)
        best_plan = candidates[0]
        
        logger.info("🏆 [ASH:v20] Selected optimal strategy: %s (Prob: %s)", 
                    best_plan["strategy"], best_plan["success_prob"])
        
        return {
            "node_id": node_id,
            "selected_strategy": best_plan["strategy"],
            "confidence": best_plan["success_prob"],
            "candidates": candidates
        }

def get_self_healing_selector(root: str = ".") -> SelfHealingSelector:
    from nexus.learning.latent_predictor_v20 import get_latent_forecaster
    predictor = get_latent_forecaster(root)
    return SelfHealingSelector(predictor)
