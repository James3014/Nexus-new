from typing import List, Dict, Any, Literal
from dataclasses import dataclass
from nexus.feedback.contracts import FailurePattern

@dataclass(frozen=True)
class RetryAction:
    """[NEXUS v26.7] 重試策略指令"""
    action: Literal["EXPLORE", "RESAMPLE", "ABSTAIN"]
    strategies: List[str]
    temperature: float

class RetryPolicy:
    """
    🔄 Task T5: Retry Policy (Decider)
    職責: 純粹的「指揮官」。根據 Pattern 決定行動，不干涉訊號映射。
    """
    @staticmethod
    def decide(patterns: List[FailurePattern], current_k: int) -> RetryAction:
        if not patterns:
            return RetryAction(action="ABSTAIN", strategies=[], temperature=0.7)
            
        # 1. 建立 Pattern-to-Action 映射表 (Linus: Logic follows Data)
        STRATEGY_MAP = {
            "IMPORT_ERROR": ("RESAMPLE", ["include_common_imports"], 0.8),
            "MRO_VIOLATION": ("EXPLORE", ["analyze_mro_first", "variant_shuffling"], 0.9),
            "SELECTION_LOW_CONFIDENCE": ("EXPLORE", ["rubric_injection", "temperature_reduction"], 0.4)
        }
        
        # 2. 獲取最高嚴重程度的 Pattern
        sorted_patterns = sorted(patterns, key=lambda x: x.severity, reverse=True)
        top_p = sorted_patterns[0]
        
        # 3. 執行決策
        res = STRATEGY_MAP.get(top_p.pattern_code)
        if res:
            return RetryAction(action=res[0], strategies=res[1], temperature=res[2])
            
        return RetryAction(action="ABSTAIN", strategies=[], temperature=0.7)
