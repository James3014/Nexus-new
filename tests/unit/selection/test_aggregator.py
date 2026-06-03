import unittest
from nexus.verifiers.contracts import VerifierVerdict
from nexus.selection.score_aggregator import ScoreAggregator

class TestScoreAggregator(unittest.TestCase):
    def test_aggregate_scores_and_conflicts(self):
        """[T2] 驗證：能正確彙總分數並捕捉致命衝突"""
        verdicts = [
            VerifierVerdict("syntax", "c1", True, 1.0),
            VerifierVerdict("name_sanity", "c1", False, -10.0), # 強烈負面信號
            VerifierVerdict("syntax", "c2", True, 1.0)
        ]
        
        result = ScoreAggregator.aggregate(verdicts)
        
        self.assertIn("c1", result["scores"])
        self.assertIn("c2", result["scores"])
        
        # c1 因為 name_sanity 權重為 10.0，且 failed 時懲罰加倍 (-20 * 10)
        self.assertTrue(result["scores"]["c1"] < 0)
        
        # 應捕捉到 c1 存在衝突
        self.assertIn("c1", result["conflicts"])

if __name__ == "__main__":
    unittest.main()
