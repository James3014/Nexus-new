import os
from typing import Any, Dict, List
from nexus.engine.phases.base import BasePhaseHandler
from nexus.core.state_contracts import NexusState
from scripts.engine.intent_classifier import IntentClassifier
from nexus.refactor_governance import RefactorGovernance
from nexus.core.dependency_probe import DependencyProbe

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

        # 🎯 P2: 意圖預分類 (Intent Classification)
        classifier = IntentClassifier()
        intent = classifier.classify(task)
        context["intent"] = intent
        
        if intent == "refactor_template":
            print("🖋️ [Refactor:Bias] Applying Linus Mode Governance...")
            context["refactor_plan"] = RefactorGovernance.generate_refactor_plan(
                state.task_id if hasattr(state, "task_id") else "TASK_001", 
                str(self.project_root)
            )
            context["system_bias"] = RefactorGovernance.get_linus_bias()

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

        # 🛰️ P5.2: 依賴圖探針 (DepProbe) 掃描
        # 針對計畫中的 target_files 進行物理依賴感應
        probe = DependencyProbe(str(self.project_root))
        probe.build_index()
        
        # 假設從 context 中取得預計修改的檔案清單 (Mocked targets for P)
        target_files = context.get("target_files", ["main.py"]) 
        impact_map = {}
        max_risk = "LOW"
        
        for t in target_files:
            impact = probe.full_impact(t)
            impact_map[t] = impact
            if impact["risk_level"] == "HIGH":
                max_risk = "HIGH"
                print(f"⚠️ [DepProbe:HIGH] Critical dependency found for {t}. Force RESEARCH.")

        state.metadata["impact_map"] = impact_map
        state.metadata["max_risk_level"] = max_risk
        
        # 🛰️ [NSP:Dispatch] Optimized Node Selection: node_id
        # ...
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
