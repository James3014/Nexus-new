from typing import List, Dict, Optional
from nexus.committee.models import ProposalCandidate, CriticVerdict, ComparatorVote

class BordaComparator:
    """⚖️ Task T7: Borda Selector"""
    @staticmethod
    def select_winner(candidates: List[ProposalCandidate], verdicts: List[CriticVerdict]) -> Optional[str]:
        if not candidates: return None
        
        # 建立候選者得分表
        scores = {c.candidate_id: 0.0 for c in candidates}
        
        # 聚合 Critic 分數
        for v in verdicts:
            if v.candidate_id in scores:
                scores[v.candidate_id] += v.score if v.passed else -10.0 # 懲罰未通過驗證者
        
        # 找出最高分
        sorted_candidates = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        winner_id, top_score = sorted_candidates[0]
        
        return winner_id if top_score > -5.0 else None # 若全部都 fail 則無 winner
