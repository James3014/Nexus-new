import logging
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class PPhase(Enum):
    P1_RESEARCH = "P1_RESEARCH"
    P2_DESIGN = "P2_DESIGN"
    P3_IMPLEMENT = "P3_IMPLEMENT"
    P4_METABOLIZE = "P4_METABOLIZE"
    P5_FEDERATE = "P5_FEDERATE"
    P6_SETTLE = "P6_SETTLE"

class PLoopManager:
    """🛡️ Nexus v25.5 P-Loop State & Evidence Manager."""
    def __init__(self, tenant_id: str = "default"):
        self.tenant_id = tenant_id
        self.current_phase = PPhase.P1_RESEARCH
        self.session_id = str(uuid.uuid4())[:8]
        self.evidence_log = []
        self.session_failures = [] # [Phase 36.6] Track failures
        self.retry_count = 0       # [Phase 36.7] Track P3 retries
        logger.info(f"🧬 [P-LOOP] Session {self.session_id} initialized at {self.current_phase.name}")

    def transition_to(self, target_phase: PPhase, evidence: Optional[Dict[str, Any]] = None):
        """🚀 Active Phase Transition with Evidence Logging."""
        old_phase = self.current_phase
        self.current_phase = target_phase
        
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "from": old_phase.name,
            "to": target_phase.name,
            "evidence": evidence or {},
            "evidence_id": f"EV-{self.session_id}-{len(self.evidence_log):03d}"
        }
        self.evidence_log.append(entry)
        logger.info(f"📊 [P-LOOP:HUD] {old_phase.name} -> {target_phase.name} | {entry['evidence_id']}")
        return entry

    def handle_retry(self, reason: str):
        """📉 P3 -> P2: Retroactive Learning Hook."""
        if self.current_phase == PPhase.P3_IMPLEMENT:
            entry = self.transition_to(PPhase.P2_DESIGN, {"retry_reason": reason, "type": "FAILURE_DRIVEN"})
            self.session_failures.append(entry)
            logger.warning(f"🔄 [P-LOOP:RETRY] Failure-As-Learning captured: {reason}")
            return entry
        return None

    def handle_p3_failure(self, error_log: str, code_snippet: str):
        """🔴 [Phase 36.7] P3 micro-learning: Capture failures immediately."""
        self.retry_count += 1
        truncated_snippet = code_snippet[:500] + "..." if len(code_snippet) > 500 else code_snippet
        failure_lesson = {
            "type": "ANTI_REGRESSION",
            "error": error_log,
            "snippet": truncated_snippet,
            "attempt": self.retry_count
        }
        # Force a transition back to P2 with the negative evidence
        entry = self.transition_to(PPhase.P2_DESIGN, failure_lesson)
        self.session_failures.append(entry)
        logger.error(f"🚫 [P-LOOP:FAIL] P3 Surgery: Captured Negative Lesson | Retry: {self.retry_count}")
        return entry

    def get_hud_status(self) -> str:
        """📡 Dashboard-ready status string (v25.5-Micro-Learning)."""
        return (f"Phase: {self.current_phase.value} | Episode: EV-{self.session_id} | "
                f"Retry: {self.retry_count} | Negative_Lessons: {len(self.session_failures)}")

# Global instance initialization hook (to be injected into Router)
def get_manager(tenant_id: str) -> PLoopManager:
    return PLoopManager(tenant_id)
