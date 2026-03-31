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
        super().__init__(project_root, run_dir, name="P", priority=100)
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

        # 🚀 Autopilot v2.0 Dispatcher (High-Dim Routing)
        node_id = self.route_to_node(task, context.get("codebase", ""))
        print(f"🛰️ [NSP:Dispatch] Optimized Node Selection: {node_id}")

        # 🔮 P10.2 VectorRAG Context Injection (Respect Ablation Switch)
        memory_state = os.environ.get("NEXUS_MEMORY_STATE", "ON")
        if memory_state == "ON":
            try:
                from nexus.core.vector_rag import VectorRAG
                rag = VectorRAG()
                history_hits = rag.query(task, k=5)
                experience_block = rag.format_for_prompt(history_hits)
                if experience_block:
                    print(f"🧠 [RAG:Inject] Context Found. Boosting Pattern Reuse.")
                    context["experience_context"] = experience_block
            except Exception as e:
                print(f"⚠️ [RAG:Fail] Could not inject context: {e}")
        else:
            print(f"⚪ [RAG:Off] Running Baseline (Ablation Mode).")

        prediction = self.predictor.predict(task, context)
        # ... 
        return {
            "intent_pass": True,
            "best_node": node_id,
            "risk_score": prediction["risk_score"], 
            "risks": prediction["reasons"], 
            "risk_level": prediction["risk_level"],
            "tokens_used": prediction.get("tokens_used", 0)
        }

    def route_to_node(self, task_desc: str, codebase: str = "") -> str:
        """🛰️ 執行高維調度。"""
        try:
            from nexus.autopilot.v2_dispatcher import HighDimDispatcher
            dispatcher = HighDimDispatcher(self.project_root)
            return dispatcher.dispatch(task_desc, codebase)
        except Exception as e:
            print(f"⚠️ [Dispatcher] Fallback to LOCAL due to: {e}")
            return "LOCAL_HARDENED"

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
