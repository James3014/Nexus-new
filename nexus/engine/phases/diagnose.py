#!/usr/bin/env python3
from typing import Any, Dict, List, Optional, Tuple
import logging
from nexus.engine.phases.base import BasePhaseHandler
from nexus.core.state_contracts import NexusState
from nexus.learning.knowledge_index import KnowledgeIndex
from nexus.services.spec_guard_v2 import SpecGuardV2

logger = logging.getLogger(__name__)

class DiagnosticPhaseHandler(BasePhaseHandler):
    """
    🧠 Phase D: Diagnose
    組裝診斷包並注入歷史技能知識。
    """
    def __init__(self, project_root: Any, run_dir: Any, hub: Any):
        super().__init__(project_root, run_dir, name="D", priority=250)
        self.hub = hub
        self.guard = SpecGuardV2()

    def run(self, state: NexusState, context: Dict[str, Any]) -> Dict[str, Any]:
        task_desc = state.metadata.get("task_description", "")
        task_type = state.task_id.split("-")[0] if "-" in state.task_id else "bug"
        prediction = context.get("prediction")
        research_pack = context.get("research_pack")

        logger.info("🧠 [D-Stage] Assembling diagnosis pack for task: %s", task_desc)
        
        if task_type == "bug":
            pack = self.hub.assemble_diag_pack([], task_desc)
        else:
            pack = self.hub.assemble_feature_pack(plan=prediction)

        if research_pack:
            pack["research_context"] = research_pack
            pack["research_pack"] = research_pack

        try:
            knowledge_index = KnowledgeIndex(self.project_root, use_embedding=True)
            similar_skills = knowledge_index.search_similar(task_desc, top_k=3, threshold=0.1, task_type=task_type)
            if similar_skills:
                pack["learned_skills"] = [
                    {
                        "name": fm.name, "description": fm.description[:200], "task_type": fm.task_type,
                        "keywords": fm.keywords[:5], "score": round(score, 3), "skill_id": fm.task_id,
                        "plan_strategy": fm.plan_strategy, "winning_hypothesis": fm.winning_hypothesis,
                        "phantom_patterns": fm.phantom_patterns, "cycle_count": fm.cycle_count,
                        "cycle_root_cause": fm.cycle_root_cause, "verification_commands": fm.verification_commands,
                    }
                    for fm, score in similar_skills
                ]
                state.metadata["matched_skills_count"] = len(similar_skills)
                logger.info("🧠 Found %d similar learned skills", len(similar_skills))
        except Exception as skill_exc:
            logger.warning("learned_skill_lookup_failed: %s", skill_exc)
            
        # 🛡️ [Phase 2.1] SpecGuard 抗幻核驗 (Doc Grounding Hook)
        guard_result = self.guard.validate_diagnosis(pack, context)
        
        if guard_result.get("status") == "HARD_VETO":
            pack["spec_veto"] = guard_result
            # 注入 Veto 標記供 Orchestrator 觀測內容及性能性能性能
            pack["fail"] = True
            pack["veto_reason"] = "Doc conflict detected by SpecGuard"
            logger.error("🛡️ [D-Stage:VETO] Diagnosis rejected due to official doc conflict.")
            
        return pack
