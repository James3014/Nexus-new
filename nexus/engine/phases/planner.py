from typing import Any, Dict, List, Optional, Tuple
import os
import re
from pathlib import Path
from nexus.engine.phases.base import BasePhaseHandler
from nexus.core.state_contracts import NexusState
from nexus.services.readability_hud import ReadabilityHUD
from nexus.refactor_governance import RefactorGovernance
from nexus.engine.phases.planner_providers import (
    IntentProvider, DependencyProvider, RAGProvider, SpecCompilerProvider,
    DefaultIntentProvider, DefaultDependencyProvider, DefaultRAGProvider, DefaultSpecCompilerProvider
)
from nexus.models.planner_models import PlannerResult

class PlannerPhaseHandler(BasePhaseHandler):
    """
    🔮 Phase P: Planning (Refactored & Decoupled)
    執行風險預判與實作包編譯。
    """
    def __init__(self, project_root: Any, run_dir: Any, 
                 predictor=None,
                 intent_provider: IntentProvider = None,
                 dependency_provider: DependencyProvider = None,
                 rag_provider: RAGProvider = None,
                 spec_provider: SpecCompilerProvider = None):
        super().__init__(project_root, run_dir, name="P", priority=100)
        from nexus.services.predictor import Predictor
        self.predictor = predictor or Predictor()
        self.intent_provider = intent_provider or DefaultIntentProvider()
        self.dependency_provider = dependency_provider or DefaultDependencyProvider()
        self.rag_provider = rag_provider or DefaultRAGProvider()
        self.spec_provider = spec_provider or DefaultSpecCompilerProvider()

    def run(self, state: NexusState, context: Dict[str, Any]) -> Dict[str, Any]:
        task = context.get("task", "")
        print(f"🔮 [Nexus:Predict] Refactored Planner scanning task: {task}")
        intent_pass, refusal_reason = self._guard_intent(task)
        if not intent_pass:
            return PlannerResult(
                intent_pass=False,
                handoff_readiness=0.0,
                risk_score=0.0,
                refusal_reason=f"{refusal_reason}（請提供更具體且非簡短描述）",
            ).model_dump()

        # 1. Intent Classification
        intent_data = self.intent_provider.classify(task)
        context["intent"] = intent_data["intent"]
        
        # 2. Dependency Probing
        target_files = context.get("target_files", ["main.py"])
        impact_map = self.dependency_provider.probe_dependencies(Path(self.project_root), target_files)
        state.metadata["impact_map"] = impact_map

        # 3. Prediction & Spec Compilation
        prediction = self.predictor.predict(task, context)
        task_lower = task.lower()
        risks: List[str] = []
        if "html" in task_lower and "js" in task_lower:
            prediction["risk_score"] = max(float(prediction.get("risk_score", 0.0)), 0.3)
            risks.append("JS conflict risk")
        if "read" in task_lower and "file" in task_lower:
            prediction["risk_score"] = max(float(prediction.get("risk_score", 0.0)), 0.8)
            risks.append("Browser sandbox risk")
        handoff_readiness = self._compile_and_audit_spec(task, prediction, state, context)

        return PlannerResult(
            intent_pass=True,
            handoff_readiness=handoff_readiness,
            risk_score=prediction.get("risk_score", 0.0),
            risks=risks,
        ).model_dump()

    def _compile_and_audit_spec(self, task, prediction, state, context) -> float:
        try:
            task_id = state.task_id if hasattr(state, "task_id") else "TASK_UNBOUND"
            compile_in = {
                "goal": task,
                "deliverables": prediction.get("deliverables", []),
                "acceptance_criteria": prediction.get("acceptance_criteria", [])
            }
            pack_results = self.spec_provider.compile_implementation_pack(Path(self.project_root), task_id, compile_in)
            return float(pack_results["audit"]["readability_score"])
        except Exception:
            return 0.0

    # Backward-compatible governance APIs (used by legacy tests/tools)
    def calculate_ambiguity_score(self, task: str) -> float:
        txt = (task or "").strip()
        if not txt:
            return 1.0

        score = 0.0
        if len(txt) < 10:
            score += 0.5
        elif len(txt) < 20:
            score += 0.25

        if not re.search(r"[A-Za-z0-9_./-]+\.py", txt):
            score += 0.25

        vague_words = ("修一下", "看一下", "處理一下", "優化一下", "功能", "東西", "問題")
        if any(w in txt for w in vague_words):
            score += 0.3

        return max(0.0, min(1.0, score))

    def _guard_intent(self, task: str) -> Tuple[bool, str]:
        score = self.calculate_ambiguity_score(task)
        if score > 0.7:
            return (
                False,
                f"🛑 [ClarificationGate] Task intent too ambiguous (score={score:.2f}).",
            )
        return True, f"✅ [ClarificationGate] Task accepted (score={score:.2f})."
