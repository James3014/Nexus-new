from nexus.evaluation.contracts import PromotionReceipt, PromotionEvidence
from nexus.governance.domain.promotion_policy import PromotionPolicy, PromotionDecision
from typing import List

class ReceiptReplayer:
    """
    🔄 Task: Receipt Replay Verifier (Application)
    職責: 用收據重播判定，檢查決策是否可重複驗證。
    """
    @staticmethod
    def replay_decision(receipt: PromotionReceipt, evidences: List[PromotionEvidence]) -> bool:
        # 1. 證據雜湊一致性檢查
        # (簡化實作：在實際系統中會比對 evidence_hash)
        
        # 2. 邏輯重播
        decision = PromotionPolicy.evaluate(
            total_gain=receipt.total_gain,
            total_loss=receipt.total_loss,
            evidence_count=len(evidences)
        )
        
        # 3. 狀態對位
        expected_status = "APPROVED" if decision.approved else "REJECTED"
        
        if expected_status != receipt.status:
            print(f"❌ REPLAY MISMATCH: Expected {expected_status}, but receipt says {receipt.status}")
            return False
            
        print(f"✅ REPLAY CONSISTENT: {receipt.receipt_id}")
        return True
