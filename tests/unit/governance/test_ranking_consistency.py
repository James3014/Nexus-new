import unittest
from nexus.governance.domain.ranking_core import RankingCore
class TestRanking(unittest.TestCase):
    def test_ranking(self):
        self.assertEqual(RankingCore.score(0.8), 80.0)
