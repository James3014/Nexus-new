import unittest
from nexus.committee.metrics.taxonomy import FailureTaxonomy

class TestFailureTaxonomy(unittest.TestCase):
    def test_valid_bucket_creation(self):
        """[T1] 驗證：能正確建立合法的失敗分類"""
        tax = FailureTaxonomy(
            main_bucket="selection_low_confidence",
            sub_bucket="tie_detected",
            evidence_ref="c1_c2_borda_gap_0.0"
        )
        self.assertEqual(tax.main_bucket, "selection_low_confidence")
        
    def test_invalid_bucket_rejection(self):
        """[T1] 驗證：非法的分類名稱應被靜態/動態阻斷"""
        with self.assertRaises(ValueError):
            FailureTaxonomy(main_bucket="random_model_error")

if __name__ == "__main__":
    unittest.main()
