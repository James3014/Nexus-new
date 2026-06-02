import unittest
from nexus.optimize.cost_policy import CostEvidencePolicy

class TestCostEvidencePolicy(unittest.TestCase):
    """
    [NEXUS v2.5] TDD Task 2: CostEvidencePolicy
    驗證：成本分類是否與執行流程解耦，且分類語義純淨。
    """
    def test_rescue_no_model_classification(self):
        # model_calls=0, total_tokens=0 應為 rescue_only_no_model_call
        res = CostEvidencePolicy.classify_cost_evidence(model_calls=0, total_tokens=0, cap_count=3)
        self.assertEqual(res, "rescue_only_no_model_call")

    def test_full_chain_delivery_classification(self):
        # model_calls > 0 且鏈路完整時為 full_chain_delivery
        res = CostEvidencePolicy.classify_cost_evidence(model_calls=1, total_tokens=1200, cap_count=8)
        self.assertEqual(res, "full_chain_delivery")

if __name__ == "__main__":
    unittest.main()
