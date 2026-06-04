import hashlib
import json
from datetime import datetime
from typing import List, Dict, Any
from nexus.evaluation.contracts import PromotionReceipt, PromotionEvidence
from nexus.governance.domain.promotion_policy import PromotionDecision

class ReceiptFactory:
    """
    🏭 Task: Governance Receipt Production (Infrastructure)
    職責: 將 Domain 決策轉化為可持久化的物理收據。
    """
    @staticmethod
    def create_receipt(decision: PromotionDecision, 
                       evidences: List[PromotionEvidence], 
                       manifest_hash: str) -> PromotionReceipt:
        
        evidence_data = str([e.task_id for e in evidences])
        evidence_hash = hashlib.sha256(evidence_data.encode()).hexdigest()
        
        receipt_id = f"R-{hashlib.md5((evidence_hash + manifest_hash).encode()).hexdigest()[:8]}"
        
        return PromotionReceipt(
            receipt_id=receipt_id,
            status="APPROVED" if decision.approved else "REJECTED",
            total_gain=sum(e.challenge_recovery_gain for e in evidences),
            total_loss=sum(e.baseline_regression_loss for e in evidences),
            evidence_hash=evidence_hash,
            verdict=decision.verdict,
            blockers=decision.blockers,
            timestamp=datetime.now().isoformat()
        )
