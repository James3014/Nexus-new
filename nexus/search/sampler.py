from typing import List, Dict, Any, Literal
from nexus.search.contracts import RetryDirective
from nexus.search.diversity import DiversityMeter
from nexus.search.feedback_router import FeedbackRouter
from nexus.verifiers.contracts import VerifierVerdict

class AdaptiveResampler:
    """
    🔄 Task T10: Verifier-Guided Retry
    職責: 結合多樣性與驗證反饋，決定最優探索策略。
    """
    def __init__(self):
        self.meter = DiversityMeter()

    def evaluate_and_decide(self, 
                           failure_bucket: str, 
                           candidate_contents: List[str], 
                           current_k: int,
                           verdicts: List[VerifierVerdict] = None) -> RetryDirective:
        
        diversity_score = self.meter.compute_diversity(candidate_contents)
        feedback = FeedbackRouter.route_failure(verdicts or [])
        
        # 1. 優先處理反饋導向的重採樣
        if feedback["feedback_loop_active"]:
            return RetryDirective(
                should_retry=True,
                mode="EXPLORE",
                modified_params={
                    "hints": feedback["retry_hints"],
                    "strategies": feedback["suggested_strategies"],
                    "temperature": 0.8
                }
            )
        
        # 2. 處理基礎分桶失敗
        if failure_bucket == "coverage_low":
            return RetryDirective(
                should_retry=True,
                mode="EXPLORE",
                modified_params={"new_k": current_k + 2, "temperature": 0.9}
            )
            
        if failure_bucket == "diversity_low" or diversity_score < 0.3:
            return RetryDirective(
                should_retry=True,
                mode="EXPLORE",
                modified_params={"variant_shuffling": True, "force_novelty": True}
            )
            
        return RetryDirective(should_retry=False, mode="WAIT", modified_params={})
