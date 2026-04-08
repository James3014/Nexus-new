from typing import Any, Dict, List, Optional, Tuple
import os
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

        # 1. Intent Classification
        intent_data = self.intent_provider.classify(task)
        context["intent"] = intent_data["intent"]
        
        # 2. Dependency Probing
        target_files = context.get("target_files", ["main.py"])
        impact_map = self.dependency_provider.probe_dependencies(Path(self.project_root), target_files)
        state.metadata["impact_map"] = impact_map

        # 3. Prediction & Spec Compilation
        prediction = self.predictor.predict(task, context)
        handoff_readiness = self._compile_and_audit_spec(task, prediction, state, context)

        return PlannerResult(
            intent_pass=True,
            handoff_readiness=handoff_readiness,
            risk_score=prediction.get("risk_score", 0.0)
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
