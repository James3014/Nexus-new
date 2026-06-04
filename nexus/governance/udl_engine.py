from dataclasses import dataclass
from typing import List

@dataclass(frozen=True)
class GovernanceHealthScore:
    score: float # 0.0 - 1.0
    status: str  # STABLE, DEGRADED, CRITICAL
    trend: str   # IMPROVING, STABLE, DECLINING

class UDLEngine:
    """
    ✨ Task 1.1: Unified Decision Language (Meta-Stable Version)
    職責: 將多維指標歸一化，並偵測長期趨勢，對異常指標實施 Clamp。
    """
    THRESHOLD_STABLE = 0.8
    THRESHOLD_CRITICAL = 0.5

    @staticmethod
    def calculate_health(policy_pass_rate, slo_budget, fitness_passed, chaos_success, history: List[float] = None) -> GovernanceHealthScore:
        # 1. 指標 Clamp (Fail-Safe)
        ppr = max(0.0, min(1.0, policy_pass_rate))
        slo = max(0.0, min(1.0, slo_budget))
        fp = 1.0 if fitness_passed else 0.0
        cs = 1.0 if chaos_success else 0.0

        # 2. 權重化計算
        raw_score = (ppr * 0.4) + (slo * 0.3) + (fp * 0.2) + (cs * 0.1)
        
        status = 'STABLE'
        if raw_score < UDLEngine.THRESHOLD_CRITICAL: status = 'CRITICAL'
        elif raw_score < UDLEngine.THRESHOLD_STABLE: status = 'DEGRADED'
        
        # 3. 趨勢偵測 (Trend Sensing)
        trend = 'STABLE'
        if history and len(history) >= 2:
            prev_score = history[-1]
            if raw_score > prev_score + 0.05: trend = 'IMPROVING'
            elif raw_score < prev_score - 0.05: trend = 'DECLINING'
            
        return GovernanceHealthScore(round(raw_score, 3), status, trend)
