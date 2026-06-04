from typing import List, Dict, Any
from dataclasses import dataclass

@dataclass(frozen=True)
class RankingCandidate:
    """[Domain] 晉升候選者"""
    task_id: str
    evidence_quality: float # 0.0 to 1.0
    oracle_gap_recovery: float
    complexity_score: float # lower is better

class CandidateRanker:
    """
    🥇 Task: Deterministic Candidate Ranking (Domain)
    職責: 基於證據品質、回收率與複雜度進行決定性排序。
    """
    @staticmethod
    def rank_candidates(candidates: List[RankingCandidate]) -> List[RankingCandidate]:
        if not candidates:
            return []
            
        # 排序權重：1. 證據品質 (優先) 2. 回收率 3. 複雜度 (倒序)
        # Linus: 消滅特殊情況，用決定性 Key
        return sorted(
            candidates,
            key=lambda c: (c.evidence_quality, c.oracle_gap_recovery, -c.complexity_score),
            reverse=True
        )
