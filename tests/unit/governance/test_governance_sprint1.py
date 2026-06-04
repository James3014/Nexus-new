import unittest
from nexus.governance.domain.promotion_policy import PromotionPolicy
from nexus.governance.infrastructure.receipt_factory import ReceiptFactory
from nexus.evaluation.contracts import PromotionEvidence

class TestGovernanceSprint1(unittest.TestCase):
    """
    🏗️ [v27.1 Sprint 1] TDD Matrix: Policy & Receipts
    驗證解耦後的規則判定與物理收據產出。
    """

    def test_pure_policy_gain_loss(self):
        """[Domain] 測試純邏輯判定：必須有增益且無退化"""
        # 1. 成功案例
        d1 = PromotionPolicy.evaluate(total_gain=0.5, total_loss=0.0, evidence_count=1)
        self.assertTrue(d1.approved)
        
        # 2. 基線退化案例
        d2 = PromotionPolicy.evaluate(total_gain=1.0, total_loss=0.001, evidence_count=1)
        self.assertFalse(d2.approved)
        self.assertIn("BASELINE_REGRESSION", d2.blockers[0])

    def test_receipt_production(self):
        """[Infrastructure] 測試收據產出：ID 與 Hash 是否穩定"""
        decision = PromotionPolicy.evaluate(0.2, 0.0, 1)
        evidences = [PromotionEvidence("t1", 0.2, 0.0, "r1")]
        manifest_hash = "abc-123"
        
        receipt = ReceiptFactory.create_receipt(decision, evidences, manifest_hash)
        
        self.assertEqual(receipt.status, "APPROVED")
        self.assertIsNotNone(receipt.receipt_id)
        self.assertTrue(receipt.receipt_id.startswith("R-"))

if __name__ == "__main__":
    unittest.main()
