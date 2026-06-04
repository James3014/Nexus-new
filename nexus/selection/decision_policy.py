from typing import Dict, List, Optional, Tuple, Any
from nexus.selection.contracts import SelectionVerdict
from nexus.abstention.policy import AbstentionPolicy

class DecisionPolicy:
    """
    ⚖️ Task T3: Decision Policy (Decision Layer)
    職責: 專門負責「是否放行」的決策，使用統一的 AbstentionPolicy。
    """
    @staticmethod
    def evaluate_and_decide(aggregated_data: Dict[str, Any], calibrated_confidence: float) -> SelectionVerdict:
        scores = aggregated_data["scores"]
        conflicts = aggregated_data["conflicts"]
        
        # 1. 執行棄權判定
        if AbstentionPolicy.should_abstain(scores, conflicts, calibrated_confidence):
            return SelectionVerdict(
                winner_id=None,
                confidence=0.0,
                gap=0.0,
                abstained=True,
                reason="ABSTAINED_BY_POLICY",
                failure_bucket="selection_low_confidence"
            )
            
        # 2. 執行選優判定
        sorted_candidates = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        winner_id, top_score = sorted_candidates[0]
        
        gap = 0.0
        if len(sorted_candidates) >= 2:
            gap = top_score - sorted_candidates[1][1]
            
        return SelectionVerdict(
            winner_id=winner_id,
            confidence=calibrated_confidence,
            gap=gap,
            abstained=False,
            reason="WINNER_SELECTED"
        )
