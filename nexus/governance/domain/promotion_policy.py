from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Literal

@dataclass(frozen=True)
class PromotionDecision:
    """[Domain] 晉升決策結果"""
    approved: bool
    verdict: str
    blockers: List[str] = field(default_factory=list)

class PromotionPolicy:
    """
    🛡️ Task: Governance Promotion Rules (Pure Domain Logic)
    職責: 實施 Gain(C) > 0 && Loss(B) == 0 的純邏輯判定。
    """
    @staticmethod
    def evaluate(total_gain: float, total_loss: float, evidence_count: int) -> PromotionDecision:
        blockers = []
        
        if evidence_count < 1:
            blockers.append("NO_EVIDENCE")
            
        if total_loss > 0:
            blockers.append(f"BASELINE_REGRESSION: {total_loss:.4f}")
            
        if total_gain <= 0:
            blockers.append("NO_CHALLENGE_GAIN")
            
        approved = not blockers
        verdict = "GOVERNANCE_PASSED" if approved else "GOVERNANCE_FAILED"
        
        return PromotionDecision(approved=approved, verdict=verdict, blockers=blockers)
