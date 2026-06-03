from typing import Dict, List, Optional, Tuple, Any
from nexus.selection.contracts import SelectionVerdict
from nexus.selection.abstain_policy import AbstainPolicy
from nexus.selection.winner_policy import WinnerPolicy

class DecisionPolicy:
    """
    ⚖️ Task T3: Decision Policy (Decision Layer)
    職責: 專門負責「是否放行」的決策，與評分邏輯解耦。
    """
    @staticmethod
    def evaluate_and_decide(aggregated_data: Dict[str, Any], base_confidence: float) -> SelectionVerdict:
        scores = aggregated_data["scores"]
        conflicts = aggregated_data["conflicts"]
        
        # 1. 執行棄權判定 (Decision Logic)
        if AbstainPolicy.should_abstain(scores, conflicts, base_confidence):
            return SelectionVerdict(
                winner_id=None,
                confidence=0.0,
                gap=0.0,
                abstained=True,
                reason="ABSTAINED_BY_POLICY",
                failure_bucket="selection_low_confidence"
            )
            
        # 2. 執行選優判定 (Winner Logic)
        winner_id, final_conf = WinnerPolicy.determine_winner(aggregated_data, base_confidence)
        
        # 3. 計算實體 Gap
        gap = 0.0
        if len(scores) >= 2:
            s_v = sorted(scores.values(), reverse=True)
            gap = s_v[0] - s_v[1]
            
        return SelectionVerdict(
            winner_id=winner_id,
            confidence=final_conf,
            gap=gap,
            abstained=False,
            reason="WINNER_SELECTED"
        )
