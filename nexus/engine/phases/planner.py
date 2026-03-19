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
        task = context.get("task", "")
        print(f"🔮 [Nexus:Predict] Scanning environment for task: {task}")
        
        # 🛡️ Trinity Intent Guard (PHA-010)
        intent_pass, refusal_reason = self._guard_intent(task)
        if not intent_pass:
            print(f"🛑 [IntentGuard] Refused: {refusal_reason}")
            return {
                "intent_pass": False,
                "refusal_reason": refusal_reason,
                "risk_score": 1.0,
                "risk_level": "BLOCK"
            }

        prediction = self.predictor.predict(task, context)
        # ... 
        return {
            "intent_pass": True,
            "risk_score": prediction["risk_score"], 
            "risks": prediction["reasons"], 
            "risk_level": prediction["risk_level"],
            "tokens_used": prediction.get("tokens_used", 0)
        }

    def _guard_intent(self, task: str) -> tuple[bool, str]:
        """🛡️ 檢查意圖是否模糊 (Heuristic)"""
        # 放寬長度限制並支援 OFF- 系列任務編號 (v9-Audit-Fix)
        if len(task) < 5:
            return False, "指令過於簡短，請描述具體目標。"
        
        # 如果是明確的基準測試任務 ID，直接放行
        if task.startswith("OFF-") or task.startswith("FEAT-"):
            return True, ""

        fuzzy_keywords = ["改一下", "改改", "修一下", "弄好"]
        if any(kw in task for kw in fuzzy_keywords) and "/" not in task:
            return False, "檢測到模糊指令且未指定路徑。"
            
        return True, ""
