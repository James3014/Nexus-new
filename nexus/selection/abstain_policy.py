from typing import Dict, List, Any

class AbstainPolicy:
    """
    🏳️ Task T3: Abstain Policy (Selection Lane)
    職責: 依據彙總後的分數與衝突狀態，決定是否需要「棄權」。
    """
    @staticmethod
    def should_abstain(scores: Dict[str, float], conflicts: List[str], confidence: float) -> bool:
        if not scores:
            return True
        
        sorted_scores = sorted(scores.values(), reverse=True)
        # 1. 全部都是負分 (全面崩潰)
        if sorted_scores[0] < 0:
            return True
            
        # 2. Top 2 平手或差距極小
        if len(sorted_scores) >= 2:
            gap = sorted_scores[0] - sorted_scores[1]
            if gap < 0.1: # 差距極小
                return True
                
        # 3. 雖然有 Winner 但它存在致命衝突信號
        if conflicts:
            # 在最嚴謹模式下，任何衝突都導致棄權
            return True
            
        # 4. 基礎信心不足
        if confidence < 0.4:
            return True
            
        return False
