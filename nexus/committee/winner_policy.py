from typing import List, Dict, Optional, Tuple
from nexus.committee.score_aggregator import ScoreAggregator
from nexus.committee.abstain_policy import AbstainPolicy

class WinnerPolicy:
    """
    🏅 Task T4: Winner Policy
    職責: 結合分數彙總與棄權政策，決定最終的 Winner。
    """
    @staticmethod
    def determine_winner(scores: Dict[str, float], confidence: float) -> Tuple[Optional[str], float]:
        # 1. 檢查是否應棄權
        if AbstainPolicy.should_abstain(scores, confidence):
            return None, 0.0
            
        # 2. Borda 決策邏輯
        sorted_candidates = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        winner_id, top_score = sorted_candidates[0]
        
        # 3. 計算信心增益 (Gap between top 2)
        win_confidence = confidence
        if len(sorted_candidates) >= 2:
            gap = top_score - sorted_candidates[1][1]
            if gap > 5.0: win_confidence += 0.2 # 強證據增益
            
        return winner_id, min(1.0, win_confidence)
