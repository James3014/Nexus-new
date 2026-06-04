import unittest
from nexus.governance.domain.candidate_ranker import CandidateRanker, RankingCandidate

class TestGovernanceSprint2(unittest.TestCase):
    """
    🏗️ [v27.1 Sprint 2] TDD Matrix: Candidate Ranking
    驗證確定性排序邏輯。
    """

    def test_deterministic_ranking(self):
        """[Domain] 測試排序優先級：證據品質 > 回收率 > 複雜度"""
        c1 = RankingCandidate("t1", evidence_quality=0.8, oracle_gap_recovery=0.5, complexity_score=10)
        c2 = RankingCandidate("t2", evidence_quality=0.9, oracle_gap_recovery=0.4, complexity_score=20) # 證據品質勝
        c3 = RankingCandidate("t3", evidence_quality=0.8, oracle_gap_recovery=0.6, complexity_score=15) # 同品質，回收率勝
        c4 = RankingCandidate("t4", evidence_quality=0.8, oracle_gap_recovery=0.6, complexity_score=5)  # 同品質同回收，低複雜度勝
        
        ranked = CandidateRanker.rank_candidates([c1, c2, c3, c4])
        
        # 預期順序: c2 (Q:0.9) -> c4 (Q:0.8, R:0.6, C:5) -> c3 (Q:0.8, R:0.6, C:15) -> c1 (Q:0.8, R:0.5)
        self.assertEqual(ranked[0].task_id, "t2")
        self.assertEqual(ranked[1].task_id, "t4")
        self.assertEqual(ranked[2].task_id, "t3")
        self.assertEqual(ranked[3].task_id, "t1")

    def test_ranking_empty(self):
        self.assertEqual(CandidateRanker.rank_candidates([]), [])

if __name__ == "__main__":
    unittest.main()
