import logging
from typing import Dict, Any, Optional
from nexus.engine.audit_rejection_receipt import AuditRejectionReceipt

logger = logging.getLogger(__name__)

class MicroSwarmTrigger:
    """
    🛡️ MicroSwarmTrigger: 微蜂群觸發器
    根據治理訊號判定是否啟動受控並行探索。
    """
    
    ELIGIBLE_FAILURE_CLASSES = {
        "semantic_incomplete",
        "operator_semantics_unclear",
        "constraint_satisfied_but_behavior_wrong",
        "semantic_reasoning_ceiling",
        "operator_semantics_probe"
    }

    BLOCKER_CLASSES = {
        "env_parity_defect",
        "sandbox_restricted",
        "telemetry_incomplete",
        "syntax_error"
    }

    def should_trigger(
        self, 
        state_metadata: Dict[str, Any], 
        rejection_receipt: Optional[AuditRejectionReceipt],
        attempt: int
    ) -> bool:
        # 1. 基礎物理條件檢查
        if attempt < 2:
            return False # 至少要有一次失敗重試

        if not rejection_receipt:
            return False

        # 2. 檢測語義型失敗 (符合則觸發)
        failure_class = rejection_receipt.rejection_class.lower()
        
        if failure_class in self.BLOCKER_CLASSES:
            logger.info("🚫 [SwarmTrigger] Blocker detected (%s). Swarm forbidden.", failure_class)
            return False

        if failure_class in self.ELIGIBLE_FAILURE_CLASSES:
            # 3. 檢查 Context 質量 (避免 Context Bloat 時啟動)
            context_quality = state_metadata.get("context_quality_score", 1.0)
            if context_quality < 0.5:
                logger.warning("⚠️ [SwarmTrigger] Context quality too low (%s). Swarm suppressed.", context_quality)
                return False
            
            logger.info("🐝 [SwarmTrigger] Semantic failure detected (%s). Swarm ELIGIBLE.", failure_class)
            return True

        return False
