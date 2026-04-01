import logging
from typing import Dict, Any, List, Optional
from nexus.learning.latent_predictor_v20 import LatentPredictorV20
from nexus.core.ash_matrix import ASHMatrix
from nexus.core.ash_template_resolver import ASHTemplateResolver
from nexus.core.ash_contracts import ASHExecutionPlan

logger = logging.getLogger(__name__)

class SelfHealingSelector:
    """
    🛡️ Nexus v24 Adaptive Self-Healing (ASH) Selector
    職責: 基於外部注入的 ASH Matrix 與 Template Resolver，對蜂群失敗進行戰略計畫編排。
    """
    
    def __init__(self, predictor: LatentPredictorV20, matrix: ASHMatrix, resolver: ASHTemplateResolver):
        self.predictor = predictor
        self.matrix = matrix
        self.resolver = resolver # 注入解析器內容及性能。

    def rank_strategies(self, task_desc: str, failure_context: str, env: str = "dev") -> List[Dict[str, Any]]:
        """
        🚀 戰略預演：對矩陣中的各修復選項進行成功率排序與計畫展開預覽其性質性質內容分析。
        """
        logger.info("📡 [ASH:v24] Ranking self-healing strategies for failure: %s", task_desc[:50])
        
        ranked = []
        context = {"env": env, "task_desc": task_desc, "failure_context": failure_context}
        
        for s_id, strat in self.matrix.strategies.items():
            # 1. 物理具現執行計畫內容解析及對度。
            try:
                # 這裡執行解析器，將標籤鏈展開為具體參數計畫內容及其性質。
                plan = self.resolver.resolve(strat, context)
            except Exception as e:
                logger.warning("⚠️ [ASHSelector] Skipping strategy [%s] due to resolution error: %s", s_id, e)
                continue

            # 2. 物理對位：預測 ROI
            prediction = self.predictor.forecast_roi(f"Self-heal via {s_id}: {task_desc}")
            success_prob = strat.success_base * prediction["roi_score"]
            
            # 3. 風險懲罰內容及其性質分析。內容、及性能。
            risk = self.predictor.predict_risk(failure_context)
            if risk["status"] == "CAUTION":
                success_prob *= (1.0 - risk["reject_prob"])
                
            ranked.append({
                "strategy": s_id,
                "success_prob": round(success_prob, 2),
                "prediction": prediction,
                "risk_status": risk["status"],
                "plan": plan # 帶回完整的 ASHExecutionPlan 對象其性能內容分析性能。性能分析。
            })
            
        return sorted(ranked, key=lambda x: x["success_prob"], reverse=True)

    def trigger_ash(self, node_id: str, task_desc: str, failure_context: str, env: str = "dev") -> Dict[str, Any]:
        """
        具現化自癒決策：返回最佳執行計畫其內容內容及性能。性能分析。
        """
        logger.warning("🚨 [ASH:v24] Node [%s] failed. Triggering adaptive repair...", node_id)
        
        candidates = self.rank_strategies(task_desc, failure_context, env=env)
        if not candidates:
            return {"status": "FAILED", "reason": "No valid strategies found."}
            
        best_candidate = candidates[0]
        best_plan = best_candidate["plan"]
        
        logger.info("🏆 [ASH:v24] Selected optimal plan: %s (Prob: %s, Commands: %d)", 
                    best_plan.strategy_id, best_candidate["success_prob"], len(best_plan.commands))
        
        return {
            "node_id": node_id,
            "selected_strategy": best_plan.strategy_id,
            "confidence": best_candidate["success_prob"],
            "plan": best_plan,
            "candidates": candidates
        }

def get_self_healing_selector(root: str = ".", env: str = "dev") -> SelfHealingSelector:
    """物理工廠：升級為具備 Resolver 注入之自癒選擇器具現化入口。"""
    from nexus.learning.latent_predictor_v20 import get_latent_forecaster
    from nexus.core.ash_matrix import ASHMatrixLoader
    from nexus.core.ash_template_loader import ASHTemplateLoader
    from nexus.core.ash_template_resolver import ASHTemplateResolver
    
    predictor = get_latent_forecaster(root)
    matrix = ASHMatrixLoader.load(root, env=env)
    
    # Phase 4: 載入模板並具現化解析器其性能及對度解析內容及其對等內容分析性能。性能分析。
    templates = ASHTemplateLoader.load(root)
    resolver = ASHTemplateResolver(templates)
    
    return SelfHealingSelector(predictor, matrix, resolver)
