from typing import List, Optional, Dict

class AbstainPolicy:
    """
    🏳️ Task T3: Abstain Policy
    職責: 在證據不足或嚴重衝突時決定「棄權」，防止錯選。
    """
    @staticmethod
    def should_abstain(scores: Dict[str, float], confidence: float) -> bool:
        if not scores:
            return True
        
        sorted_scores = sorted(scores.values(), reverse=True)
        # 1. 平手判定 (Top 2 分數過於接近)
        if len(sorted_scores) >= 2:
            gap = sorted_scores[0] - sorted_scores[1]
            if gap < 0.1: # 差距極小
                print("⚠️ [Abstain] Tie detected. Gap too small.")
                return True
                
        # 2. 低信心判定
        if confidence < 0.4:
            print(f"⚠️ [Abstain] Low confidence: {confidence}")
            return True
            
        # 3. 全面崩潰判定 (最高分也是負分)
        if sorted_scores[0] < 0:
            return True
            
        return False
