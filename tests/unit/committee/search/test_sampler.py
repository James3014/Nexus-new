import unittest
from nexus.search.sampler import AdaptiveResampler, directive_to_dict
from nexus.retry_policy.policy import RetryAction

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

    def test_verifier_feedback_takes_priority(self):
        """[T10] 驗證：Verifier 反饋經 FeedbackRouter/RetryPolicy 產出重試指令"""
        feedback = RetryAction(action="RESAMPLE", strategies=["include_common_imports"], temperature=0.8)
        action = AdaptiveResampler().evaluate_and_decide(
            failure_bucket="coverage_low",
            candidate_contents=["pd.DataFrame()"],
            current_k=1,
            feedback_action=feedback,
            pattern_codes=["IMPORT_ERROR"],
        )
        self.assertTrue(action.should_retry)
        self.assertEqual(action.mode, "EXPLOIT")
        self.assertEqual(action.modified_params["source"], "verifier_feedback")
        self.assertEqual(action.modified_params["patterns"], ["IMPORT_ERROR"])
        self.assertIn("include_common_imports", action.modified_params["strategies"])

    def test_no_signal_waits(self):
        action = AdaptiveResampler().evaluate_and_decide(
            failure_bucket=None,
            candidate_contents=["alpha beta", "gamma delta"],
            current_k=2,
        )
        self.assertFalse(action.should_retry)
        self.assertEqual(directive_to_dict(action)["mode"], "WAIT")

if __name__ == "__main__":
    unittest.main()
