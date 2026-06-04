import unittest
from nexus.evaluation.promotion_engine import PromotionEngine
from nexus.evaluation.contracts import PromotionEvidence

class TestPromotionEngine(unittest.TestCase):
    """
    📈 [v27] PromotionEngine 測試清單 (Hardened)
    驗證「收據驅動晉升」的嚴格治理邏輯。
    """

    def test_promotion_approved(self):
        """[T1] 理想晉升：攻堅有獲益，穩定組零退化"""
        evidences = [
            PromotionEvidence(task_id="c1", challenge_recovery_gain=1.0, baseline_regression_loss=0.0, receipt_id="r1")
        ]
        res = PromotionEngine.evaluate_promotion(evidences)
        self.assertEqual(res.status, "APPROVED")
        self.assertEqual(res.verdict, "GOVERNANCE_PASSED")

    def test_promotion_rejected_by_regression(self):
        """[T2] 拒絕晉升：導致了基線退化"""
        evidences = [
            PromotionEvidence(task_id="b1", challenge_recovery_gain=0.0, baseline_regression_loss=0.1, receipt_id="r2")
        ]
        res = PromotionEngine.evaluate_promotion(evidences)
        self.assertEqual(res.status, "REJECTED")
        self.assertTrue(any("BASELINE_REGRESSION" in b for b in res.blockers))

    def test_promotion_rejected_by_no_gain(self):
        """[T3] 拒絕晉升：無實質增益"""
        evidences = [
            PromotionEvidence(task_id="c1", challenge_recovery_gain=0.0, baseline_regression_loss=0.0, receipt_id="r1")
        ]
        res = PromotionEngine.evaluate_promotion(evidences)
        self.assertEqual(res.status, "REJECTED")
        self.assertIn("NO_CHALLENGE_GAIN", res.blockers)

    def test_promotion_rejected_empty(self):
        """[T4] 拒絕晉升：無物理證據"""
        res = PromotionEngine.evaluate_promotion([])
        self.assertEqual(res.status, "REJECTED")
        self.assertEqual(res.verdict, "NO_EVIDENCE_PROVIDED")

if __name__ == "__main__":
    unittest.main()
