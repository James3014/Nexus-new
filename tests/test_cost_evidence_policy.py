import unittest
from nexus.optimize.cost_policy import CostEvidencePolicy

class TestCostEvidencePolicy(unittest.TestCase):
    def test_rescue_only_classification(self):
        """Task 2: model_calls=0 分類為 rescue-only"""
        receipt = {"model_calls": 0, "total_tokens": 0, "capability_count": 3}
        res = CostEvidencePolicy.classify_cost_evidence(receipt)
        self.assertEqual(res, "rescue_only_no_model_call")

if __name__ == "__main__":
    unittest.main()
