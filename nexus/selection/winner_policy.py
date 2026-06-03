from typing import Dict, List, Optional, Tuple, Any
from nexus.selection.score_aggregator import ScoreAggregator
from nexus.selection.abstain_policy import AbstainPolicy

class WinnerPolicy:
    """
    🏅 Task T4: Winner Policy (Selection Lane)
    職責: 基於彙總與棄權政策，決定最終獲勝者。
    """
    @staticmethod
    def determine_winner(aggregated_data: Dict[str, Any], base_confidence: float) -> Tuple[Optional[str], float]:
        scores = aggregated_data["scores"]
        conflicts = aggregated_data["conflicts"]
        
        if AbstainPolicy.should_abstain(scores, conflicts, base_confidence):
            return None, 0.0
            
        sorted_candidates = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        winner_id, top_score = sorted_candidates[0]
        
        win_confidence = base_confidence
        if len(sorted_candidates) >= 2:
            gap = top_score - sorted_candidates[1][1]
            if gap > 15.0: # 高 Gap 門檻，證明受到強烈領域信號支持
                win_confidence = min(1.0, win_confidence + 0.3)
            
        return winner_id, win_confidence
