from typing import List, Dict, Any, Literal
from dataclasses import dataclass
from nexus.feedback.contracts import FeedbackDirective

@dataclass(frozen=True)
class RetryAction:
    """[NEXUS v26.7] 重試決策輸出"""
    action: Literal["EXPLORE", "RESAMPLE", "PACK_UPGRADE", "ABSTAIN"]
    strategies: List[str]
    temperature: float

class RetryPolicy:
    """
    🔄 Task T3: Retry Policy
    職責: 根據 Feedback Directive 決定下一步行動。
    """
    @staticmethod
    def decide(directive: FeedbackDirective, current_k: int) -> RetryAction:
        if not directive.is_actionable:
            return RetryAction("ABSTAIN", [], 0.7)
            
        # 如果有嚴重的模式 (如 MRO 損毀)，強迫 EXPLORE
        for p in directive.identified_patterns:
            if p.severity >= 0.9:
                return RetryAction("EXPLORE", directive.retry_hints + ["hierarchy_repair"], 0.9)
                
        return RetryAction("RESAMPLE", directive.retry_hints, 0.8)
