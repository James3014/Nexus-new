import unittest
from nexus.selection.winner_policy import WinnerPolicy

class TestWinnerPolicy(unittest.TestCase):
    def test_determine_winner_success(self):
        """[T4] 驗證：成功選出 winner 並提昇 confidence"""
        data = {
            "scores": {"c1": 25.0, "c2": 5.0},
            "conflicts": []
        }
        winner, conf = WinnerPolicy.determine_winner(data, 0.6)
        self.assertEqual(winner, "c1")
        # 差距 > 15.0，信心加 0.3
        self.assertAlmostEqual(conf, 0.9)

    def test_determine_winner_abstain(self):
        """[T4] 驗證：委派 AbstainPolicy 並正確回傳"""
        data = {
            "scores": {"c1": 25.0, "c2": 5.0},
            "conflicts": ["c1"] # 模擬衝突
        }
        winner, conf = WinnerPolicy.determine_winner(data, 0.6)
        self.assertIsNone(winner)
        self.assertEqual(conf, 0.0)

if __name__ == "__main__":
    unittest.main()
