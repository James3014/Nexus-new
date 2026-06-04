import unittest
from nexus.committee.models import CriticVerdict
from nexus.committee.score_aggregator import ScoreAggregator
from nexus.committee.winner_policy import WinnerPolicy

class TestSelectionLane(unittest.TestCase):
    def test_tie_abstain_logic(self):
        """驗證：平手時自動棄權"""
        scores = {"c1": 10.0, "c2": 9.95} # 差距 0.05
        winner, conf = WinnerPolicy.determine_winner(scores, 0.8)
        self.assertIsNone(winner)

    def test_strong_winner_logic(self):
        """驗證：強證據時選出 Winner"""
        scores = {"c1": 20.0, "c2": 5.0}
        winner, conf = WinnerPolicy.determine_winner(scores, 0.8)
        self.assertEqual(winner, "c1")
        self.assertGreater(conf, 0.8)

if __name__ == "__main__":
    unittest.main()
