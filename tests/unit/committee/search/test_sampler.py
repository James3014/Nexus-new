import unittest
from nexus.search.sampler import AdaptiveResampler

class TestAdaptiveResampler(unittest.TestCase):
    def test_coverage_failure_trigger(self):
        """[T8] 驗證：當 coverage_low 時，觸發 EXPLORE (多樣化) 模式"""
        resampler = AdaptiveResampler()
        action = resampler.evaluate_and_decide(
            failure_bucket="coverage_low",
            candidate_contents=["content1", "content2"],
            current_k=3
        )
        self.assertEqual(action.mode, "EXPLORE")

    def test_diversity_low_trigger(self):
        """[T2] 驗證：低多樣性補丁觸發 EXPLORE"""
        resampler = AdaptiveResampler()
        # 提供極端接近的補丁
        action = resampler.evaluate_and_decide(
            failure_bucket="selection_low_confidence",
            candidate_contents=["pass", "pass "],
            current_k=3
        )
        self.assertTrue(action.should_retry)
        self.assertTrue(action.modified_params["variant_shuffling"])

if __name__ == "__main__":
    unittest.main()
