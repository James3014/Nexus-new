import unittest
from nexus.search.retry_controller import AdaptiveRetryController

class TestAdaptiveRetryController(unittest.TestCase):
    def test_coverage_low_strategy(self):
        """[T1.3] 驗證：針對 coverage_low 的 EXPLORE 指令"""
        ctrl = AdaptiveRetryController()
        res = ctrl.compute_directive("coverage_low", 0.5, 3)
        self.assertTrue(res.should_retry)
        self.assertEqual(res.mode, "EXPLORE")
        self.assertGreater(res.modified_params["new_k"], 3)

    def test_diversity_low_strategy(self):
        """[T1.3] 驗證：針對 diversity_low 的 SHUFFLE 指令"""
        ctrl = AdaptiveRetryController()
        # 即使 bucket 不是 diversity_low，但分數太低也應觸發
        res = ctrl.compute_directive("selection_low_confidence", 0.1, 3)
        self.assertTrue(res.should_retry)
        self.assertTrue(res.modified_params["variant_shuffling"])

if __name__ == "__main__":
    unittest.main()
