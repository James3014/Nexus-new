from dataclasses import dataclass
from typing import List

@dataclass(frozen=True)
class GovernanceHealthScore:
    score: float # 0.0 - 1.0
    status: str  # STABLE, DEGRADED, CRITICAL
    trend: str   # IMPROVING, STABLE, DECLINING

class UDLEngine:
    """
    ✨ Task M1: Unified Decision Language (Meta-Stable Version)
    職責: 將多維指標歸一化，並偵測長期趨勢，避免局部信號被平均值掩蓋。
    """
    THRESHOLD_STABLE = 0.8
    THRESHOLD_CRITICAL = 0.5

    @staticmethod
    def calculate_health(policy_pass_rate, slo_budget, fitness_passed, chaos_success, history: List[float] = None) -> GovernanceHealthScore:
        # 權重化計算 (SoC: 結構純度佔 20%, 韌性佔 10%)
        raw_score = (policy_pass_rate * 0.4) + (slo_budget * 0.3) + (1.0 if fitness_passed else 0) * 0.2 + (1.0 if chaos_success else 0) * 0.1
        
        status = 'STABLE'
        if raw_score < UDLEngine.THRESHOLD_CRITICAL: status = 'CRITICAL'
        elif raw_score < UDLEngine.THRESHOLD_STABLE: status = 'DEGRADED'
        
        # 趨勢偵測 (Trend Sensing)
        trend = 'STABLE'
        if history and len(history) >= 2:
            prev_score = history[-1]
            if raw_score > prev_score + 0.05: trend = 'IMPROVING'
            elif raw_score < prev_score - 0.05: trend = 'DECLINING'
            
        return GovernanceHealthScore(round(raw_score, 3), status, trend)
