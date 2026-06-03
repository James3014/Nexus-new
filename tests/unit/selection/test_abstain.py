import unittest
from nexus.selection.abstain_policy import AbstainPolicy

class TestAbstainPolicy(unittest.TestCase):
    def test_tie_detected(self):
        """[T3] 驗證：差距過小應棄權"""
        scores = {"c1": 10.0, "c2": 9.95}
        self.assertTrue(AbstainPolicy.should_abstain(scores, [], 0.9))

    def test_conflict_detected(self):
        """[T3] 驗證：存在致命衝突應棄權"""
        scores = {"c1": 50.0, "c2": 10.0}
        self.assertTrue(AbstainPolicy.should_abstain(scores, ["c1"], 0.9))

    def test_low_confidence(self):
        """[T3] 驗證：基礎信心不足應棄權"""
        scores = {"c1": 50.0, "c2": 10.0}
        self.assertTrue(AbstainPolicy.should_abstain(scores, [], 0.3))

    def test_valid_winner(self):
        """[T3] 驗證：條件滿足時不棄權"""
        scores = {"c1": 50.0, "c2": 10.0}
        self.assertFalse(AbstainPolicy.should_abstain(scores, [], 0.9))

if __name__ == "__main__":
    unittest.main()
