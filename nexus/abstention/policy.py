from typing import Dict, List, Any, Optional
from dataclasses import dataclass

@dataclass(frozen=True)
class RiskProfile:
    """[NEXUS v26.7] 棄權風險配置文件"""
    min_confidence: float = 0.40
    min_gap: float = 0.05
    allow_conflicts: bool = False

class AbstentionPolicy:
    """
    🏳️ Task T4: Abstention Policy (Unified Decision Layer)
    職責: 基於校準後的數據執行「終極棄權判定」。
    """
    @staticmethod
    def should_abstain(scores: Dict[str, float], 
                       conflicts: List[str], 
                       calibrated_confidence: float,
                       profile: RiskProfile = RiskProfile()) -> bool:
        if not scores:
            return True
        
        sorted_scores = sorted(scores.values(), reverse=True)
        # 1. 全部都是負分 (全面崩潰)
        if sorted_scores[0] < 0:
            return True
            
        # 2. 信心過低
        if calibrated_confidence < profile.min_confidence:
            return True
            
        # 3. 差距不足 (Low Identifiability)
        if len(sorted_scores) >= 2:
            gap = sorted_scores[0] - sorted_scores[1]
            if gap < profile.min_gap:
                return True
        elif len(sorted_scores) < 2:
            # 在委員會模式下，只有一個候選者視為證據不足 (除非未來有單一候選策略)
            return True
            
        # 4. 存在物理衝突
        if conflicts and not profile.allow_conflicts:
            return True
            
        return False
