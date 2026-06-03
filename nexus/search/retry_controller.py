from typing import Dict, Any
from nexus.search.contracts import RetryDirective

class AdaptiveRetryController:
    """
    🎮 Task T1.3: Adaptive Retry Controller
    職責: 依據失敗桶與多樣性分數，精確決定下一步探索策略。
    """
    def compute_directive(self, failure_bucket: str, diversity_score: float, current_k: int) -> RetryDirective:
        # 專攻剩餘 5% 的邏輯
        
        # 1. 如果是 coverage_low (沒命中)，必須 EXPLORE
        if failure_bucket == "coverage_low":
            return RetryDirective(
                should_retry=True,
                mode="EXPLORE",
                modified_params={"new_k": current_k + 2, "temperature": 0.9}
            )
            
        # 2. 如果是 diversity_low (同質化)，強迫 SHUFFLE
        if failure_bucket == "diversity_low" or diversity_score < 0.3:
            return RetryDirective(
                should_retry=True,
                mode="EXPLORE",
                modified_params={"variant_shuffling": True, "force_novelty": True}
            )
            
        return RetryDirective(should_retry=False, mode="WAIT", modified_params={})
