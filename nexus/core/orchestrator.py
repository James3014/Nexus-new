from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import json
import logging
from datetime import datetime

from nexus.core.config import OrchestratorConfig
from nexus.core.hubs import NexusInfraHub, NexusIntelHub, NexusGovHub
from nexus.core.belief_engine import BeliefEngine
from nexus.core.belief_contracts import AuditOutcome, BeliefGate
from nexus.core.mem_palace import MemoryPalace

logger = logging.getLogger("nexus.orchestrator")


class _NullPalace:
    def audit_action(self, *_args, **_kwargs) -> bool:
        return True


class _NullBeliefGate:
    unavailable = True

    def process_audit_outcome(self, outcome: AuditOutcome) -> dict[str, Any]:
        return {
            "status": "REJECTED",
            "accepted": False,
            "task_id": outcome.task_id,
            "assumption": outcome.assumption,
            "confidence": 0.0,
            "reason": "belief_gate_unavailable",
        }

    def assess_confidence(self, *_args, **_kwargs) -> float:
        return 0.0

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
        self.palace = getattr(infra, 'palace', None)
        self.belief_engine: BeliefGate | Any | None = getattr(intel, 'belief_engine', None)

        self.git = getattr(infra, "git", None) if infra else None
        self.llm = getattr(intel, "llm", None) if intel else None
        self.commander = getattr(intel, "commander", None) if intel else None
        
        self.execution_mode = self.mode
        self.max_strikes = 1 # 簡化測試
        if not hasattr(self.belief_engine, "process_audit_outcome"):
            try:
                self.belief_engine = BeliefEngine(self.project_root / ".nexus" / "belief_state.json")
            except Exception:
                self.belief_engine = _NullBeliefGate()
        if not hasattr(self.palace, "audit_action"):
            try:
                self.palace = MemoryPalace(str(self.project_root))
            except Exception:
                self.palace = _NullPalace()

    def _do_loop(self) -> bool:
        strike = 0
        while strike < self.max_strikes:
            strike += 1
            logger.info("🚀 [v25.5] Round %d | Mode: %s", strike, self.execution_mode)

            lessons = self.commander.get_crystal_lessons(relevance=0.8) if self.commander else []
            context_brief = "\n".join([f"💎 Lesson: {l}" for l in lessons[:3]])

            if not self.llm:
                logger.error("❌ [Orchestrator] LLM not available")
                return False

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
                    
                    self._record_audit_failure(strike=strike, rebuttal=rebuttal)
                    continue
        return False

    def _record_audit_failure(self, *, strike: int, rebuttal: str) -> None:
        outcome = AuditOutcome(
            task_id=self.task,
            assumption=f"AUDIT_FAILURE_{strike}",
            passed=False,
            evidence_id=f"REBUTTAL_{datetime.now().strftime('%H%M%S')}",
            reason=rebuttal,
        )
        if hasattr(self.belief_engine, "process_audit_outcome") and self.belief_engine is not None:
            self.belief_engine.process_audit_outcome(outcome)
            return
        if self.belief_engine is not None and hasattr(self.belief_engine, "update_belief"):
            self.belief_engine.update_belief(
                task_id=outcome.task_id,
                assumption=outcome.assumption,
                confidence=outcome.confidence if outcome.confidence is not None else 0.1,
                evidence_id=outcome.evidence_id,
            )

    def _run_adversarial_audit(self, response_data: dict) -> Tuple[bool, str]:
        summary = response_data.get("summary", "")

        if hasattr(self.palace, "audit_action") and self.palace is not None:
            try:
                if not self.palace.audit_action("D", summary):
                    return False, "Palace audit rejected"
            except Exception as exc:
                return False, f"Palace audit error: {exc}"

        if not hasattr(self.belief_engine, "assess_confidence") or self.belief_engine is None:
            return False, "Belief gate unavailable"
        try:
            confidence = self.belief_engine.assess_confidence(self.task, summary)
            if confidence is None or float(confidence) < 0.5:
                return False, "Belief confidence too low"
        except Exception as exc:
            return False, f"Belief audit error: {exc}"

        from nexus.governance.evidence_guard import NexusEvidenceGuard
        guard = NexusEvidenceGuard(self.project_root, git_hub=self.infra.git if self.infra else None)
        return guard.audit_claim(summary, self.task)

    def run_review(self) -> dict:
        """Compatibility contract: return structured review result instead of bool."""
        ok = self._do_loop()
        return {"status": "PASS" if ok else "FAIL", "passed": bool(ok)}
