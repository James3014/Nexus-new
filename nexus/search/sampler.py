from typing import List, Dict, Any
from nexus.search.contracts import RetryDirective
from nexus.search.diversity import DiversityMeter

class AdaptiveResampler:
    """
    🔄 Task T2: Diversity Feedback Loop
    職責: 基於失敗桶與實體多樣性分數決定策略。
    """
    def __init__(self):
        self.meter = DiversityMeter()

    def evaluate_and_decide(self, failure_bucket: str, candidate_contents: List[str], current_k: int) -> RetryDirective:
        diversity_score = self.meter.compute_diversity(candidate_contents)
        
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
