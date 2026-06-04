import unittest
from nexus.governance.application.receipt_replayer import ReceiptReplayer
from nexus.evaluation.contracts import PromotionReceipt, PromotionEvidence

class TestReceiptReplayer(unittest.TestCase):
    """[v27.1 Sprint 3] Receipt Replay TDD"""
    
    def test_replay_matches_original_verdict(self):
        """[P0] 驗證：重播結果與收據一致"""
        receipt = PromotionReceipt(
            receipt_id="r1", status="APPROVED", total_gain=0.5, total_loss=0.0,
            evidence_hash="h1", verdict="GOVERNANCE_PASSED"
        )
        evidences = [PromotionEvidence("t1", 0.5, 0.0, "r1")]
        
        self.assertTrue(ReceiptReplayer.replay_decision(receipt, evidences))
        
    def test_replay_rejects_inconsistency(self):
        """[P0] 驗證：邏輯不符時重播失敗"""
        # 收據說核准，但邏輯判定應拒絕 (total_loss > 0)
        receipt = PromotionReceipt(
            receipt_id="r2", status="APPROVED", total_gain=0.5, total_loss=0.1,
            evidence_hash="h2", verdict="GOVERNANCE_PASSED"
        )
        evidences = [PromotionEvidence("t2", 0.5, 0.1, "r2")]
        
        self.assertFalse(ReceiptReplayer.replay_decision(receipt, evidences))

if __name__ == "__main__":
    unittest.main()
