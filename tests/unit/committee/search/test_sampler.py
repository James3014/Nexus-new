import unittest

from nexus.feedback.contracts import VerifierSignal
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

    def test_verifier_feedback_mapping(self):
        """❌ failed verifier signals map to import-aware and hierarchy retry hints"""
        resampler = AdaptiveResampler()
        action = resampler.evaluate_and_decide(
            failure_bucket="selection_low_confidence",
            candidate_contents=["pass", "pass "],
            current_k=3,
            verdicts=[
                VerifierSignal(
                    verifier_name="name_sanity",
                    passed=False,
                    score=-10.0,
                    failure_tags=["MISSING: import os"],
                ),
                VerifierSignal(
                    verifier_name="INHERITANCE_CHECK",
                    passed=False,
                    score=-20.0,
                    failure_tags=["UNDEFINED"],
                ),
            ],
        )
        self.assertTrue(action.should_retry)
        self.assertEqual(action.mode, "EXPLORE")
        self.assertIn("IMPORT_AWARE_FIX", action.modified_params["hints"])
        self.assertIn("include_common_imports", action.modified_params["strategies"])
        self.assertIn("HIERARCHY_PRESERVING", action.modified_params["hints"])
        self.assertIn("analyze_mro_first", action.modified_params["strategies"])

    def test_verifier_signal_no_feedback_falls_through(self):
        """✅ passing verifier signals keep the diversity/fallback path"""
        resampler = AdaptiveResampler()
        action = resampler.evaluate_and_decide(
            failure_bucket="selection_low_confidence",
            candidate_contents=["pass"],
            current_k=3,
            verdicts=[
                VerifierSignal(
                    verifier_name="astropy",
                    passed=True,
                    score=80.0,
                    failure_tags=[],
                )
            ],
        )
        self.assertFalse(action.should_retry)
        self.assertEqual(action.mode, "WAIT")

if __name__ == "__main__":
    unittest.main()
