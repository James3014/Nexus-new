import hashlib
from typing import List, Dict, Any, Optional
from nexus.evaluation.contracts import PromotionEvidence, PromotionReceipt

class PromotionEngine:
    """
    📈 Task: Evidence-Driven Promotion Engine (v27 Hardened)
    職責: 依據「Gain(C) > 0 && Loss(B) == 0」準則產出物理收據。
    """
    @staticmethod
    def evaluate_promotion(evidences: List[PromotionEvidence]) -> PromotionReceipt:
        receipt_id = f"PROMO-{hashlib.md5(str(evidences).encode()).hexdigest()[:8]}"
        
        if not evidences:
            return PromotionReceipt(
                receipt_id=receipt_id,
                status="REJECTED",
                total_gain=0.0,
                total_loss=0.0,
                evidence_hash="none",
                verdict="NO_EVIDENCE_PROVIDED",
                blockers=["Empty evidence list"]
            )
            
        total_gain = sum(e.challenge_recovery_gain for e in evidences)
        total_loss = sum(e.baseline_regression_loss for e in evidences)
        blockers = []
        
        # 1. 第一層閘門：證據存在性檢查
        if len(evidences) < 1:
            blockers.append("INSUFFICIENT_EVIDENCE_COUNT")
            
        # 2. 第二層閘門：數值判定 (Governance Gate)
        if total_loss > 0:
            blockers.append(f"BASELINE_REGRESSION: {total_loss:.4f}")
            
        if total_gain <= 0:
            blockers.append("NO_CHALLENGE_GAIN")
            
        status = "APPROVED" if not blockers else "REJECTED"
        verdict = "GOVERNANCE_PASSED" if not blockers else "GOVERNANCE_FAILED"
        
        return PromotionReceipt(
            receipt_id=receipt_id,
            status=status,
            total_gain=total_gain,
            total_loss=total_loss,
            evidence_hash=hashlib.sha256(str(evidences).encode()).hexdigest(),
            verdict=verdict,
            blockers=blockers
        )
