from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import json
import logging
from datetime import datetime

from nexus.core.config import OrchestratorConfig
from nexus.core.hubs import NexusInfraHub, NexusIntelHub, NexusGovHub
from nexus.core.belief_engine import BeliefEngine
from nexus.core.mem_palace import MemoryPalace

from unittest.mock import MagicMock

logger = logging.getLogger("nexus.orchestrator")

class NexusOrchestrator:
    """
    🧬 Nexus v25.5-Adversarial (RAPTOR-Aligned)
    [HARDENED] 杜絕回報造假。
    """

    def __init__(
        self,
        config: OrchestratorConfig,
        infra: Optional[NexusInfraHub] = None,
        intel: Optional[NexusIntelHub] = None,
        gov: Optional[NexusGovHub] = None,
    ):
        self.task = config.task
        self.skill_id = config.skill_id
        self.mode = config.mode
        self.project_root = Path.cwd()

        self.infra = infra
        self.intel = intel
        self.gov = gov
        self.palace = getattr(infra, 'palace', MagicMock())
        self.belief_engine = getattr(intel, 'belief_engine', MagicMock())

        self.git = infra.git if infra else None
        self.llm = intel.llm if intel else None
        self.commander = intel.commander if intel else None
        
        self.execution_mode = self.mode
        self.max_strikes = 1 # 簡化測試
        if isinstance(self.belief_engine, MagicMock):
            try:
                self.belief_engine = BeliefEngine(self.project_root / ".nexus" / "belief_state.json")
            except Exception:
                self.belief_engine = MagicMock()
        if isinstance(self.palace, MagicMock):
            try:
                self.palace = MemoryPalace(str(self.project_root))
            except Exception:
                self.palace = MagicMock()

    def _do_loop(self) -> bool:
        strike = 0
        while strike < self.max_strikes:
            strike += 1
            logger.info("🚀 [v25.5] Round %d | Mode: %s", strike, self.execution_mode)

            lessons = self.commander.get_crystal_lessons(relevance=0.8) if self.commander else []
            context_brief = "\n".join([f"💎 Lesson: {l}" for l in lessons[:3]])

            data, raw = self.llm.ask_with_template(
                task=f"{self.task}\n{context_brief}"
            )
            
            # 🛡️ [Nexus v25.5] Auditor Loop
            if data.get("status") == "PASS":
                passed, rebuttal = self._run_adversarial_audit(data)
                if passed:
                    logger.info("✅ [Audit] Evidence Verified. Complete.")
                    return True
                else:
                    logger.warning("🛑 [Audit] REJECTED: %s", rebuttal)
                    
                    # 🕵️ 修正為 4 參數對準核心：task_id, assumption, confidence, evidence_id
                    self.belief_engine.update_belief(
                        task_id=self.task,
                        assumption=f"AUDIT_FAILURE_{strike}",
                        confidence=0.1,
                        evidence_id=f"REBUTTAL_{datetime.now().strftime('%H%M%S')}"
                    ) 
                    continue
        return False

    def _run_adversarial_audit(self, response_data: dict) -> Tuple[bool, str]:
        summary = response_data.get("summary", "")

        if hasattr(self.palace, "audit_action"):
            try:
                if not self.palace.audit_action("D", summary):
                    return False, "Palace audit rejected"
            except Exception as exc:
                return False, f"Palace audit error: {exc}"

        if hasattr(self.belief_engine, "assess_confidence"):
            try:
                confidence = self.belief_engine.assess_confidence(summary)
                if confidence is not None and float(confidence) < 0.5:
                    return False, "Belief confidence too low"
            except Exception as exc:
                return False, f"Belief audit error: {exc}"

        from nexus.core.evidence_guard import NexusEvidenceGuard
        guard = NexusEvidenceGuard(self.project_root, git_hub=self.infra.git if self.infra else None)
        return guard.audit_claim(summary, self.task)
