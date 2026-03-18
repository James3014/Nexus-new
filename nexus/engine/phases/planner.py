#!/usr/bin/env python3
from typing import Any, Dict
from nexus.engine.phases.base import BasePhaseHandler
from nexus.core.state_contracts import NexusState

class PlannerPhaseHandler(BasePhaseHandler):
    """
    🔮 Phase P: Planning
    執行風險預判演算法。
    """
    def __init__(self, project_root: Any, run_dir: Any, predictor=None):
        super().__init__(project_root, run_dir)
        from nexus.services.predictor import Predictor
        self.predictor = predictor or Predictor()

    def run(self, state: NexusState, context: Dict[str, Any]) -> Dict[str, Any]:
        task = context.get("task")
        print(f"🔮 [Nexus:Predict] Scanning environment for task: {task}")
        
        prediction = self.predictor.predict(task, context)
        risk_score = prediction["risk_score"]
        risks = prediction["reasons"] # 將 reasons 映射到原本的 risks 接口
            
        print(f"⚖️ [Predict] Risk Score: {risk_score} | Detect {len(risks)} potential blockers.")
        return {
            "risk_score": risk_score, 
            "risks": risks, 
            "risk_level": prediction["risk_level"],
            "tokens_used": prediction.get("tokens_used", 0),
            "token_capture_status": "ok"
        }
