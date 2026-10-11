from typing import Any, Dict, List, Literal, Optional, Sequence

from nexus.retry_policy.policy import RetryAction
from nexus.search.contracts import RetryDirective
from nexus.search.diversity import DiversityMeter

# RetryPolicy actions map onto the search-side directive modes.
_POLICY_MODE: Dict[str, Literal["EXPLORE", "EXPLOIT"]] = {
    "EXPLORE": "EXPLORE",
    "RESAMPLE": "EXPLOIT",
}


class AdaptiveResampler:
    """
    🔄 Task T10: Verifier-Guided Retry
    職責: 結合多樣性與驗證反饋，決定最優探索策略。
    """

    def __init__(self):
        self.meter = DiversityMeter()

    def evaluate_and_decide(
        self,
        failure_bucket: Optional[str],
        candidate_contents: List[str],
        current_k: int,
        feedback_action: Optional[RetryAction] = None,
        pattern_codes: Sequence[str] = (),
    ) -> RetryDirective:

        diversity_score = self.meter.compute_diversity(candidate_contents)

        # 1. 優先處理反饋導向的重採樣 (由 Controller 完成 Mapper -> Decider 後傳入)
        action = feedback_action
        if action is not None and action.action != "ABSTAIN":
            return RetryDirective(
                should_retry=True,
                mode=_POLICY_MODE[action.action],
                modified_params={
                    "source": "verifier_feedback",
                    "patterns": list(pattern_codes),
                    "strategies": list(action.strategies),
                    "temperature": action.temperature,
                    "diversity_score": diversity_score,
                },
            )

        # 2. 處理基礎分桶失敗
        if failure_bucket == "coverage_low":
            return RetryDirective(
                should_retry=True,
                mode="EXPLORE",
                modified_params={
                    "source": "failure_bucket",
                    "new_k": current_k + 2,
                    "temperature": 0.9,
                    "diversity_score": diversity_score,
                },
            )

        if failure_bucket == "diversity_low" or diversity_score < 0.3:
            return RetryDirective(
                should_retry=True,
                mode="EXPLORE",
                modified_params={
                    "source": "diversity",
                    "variant_shuffling": True,
                    "force_novelty": True,
                    "diversity_score": diversity_score,
                },
            )

        return RetryDirective(
            should_retry=False,
            mode="WAIT",
            modified_params={"diversity_score": diversity_score},
        )


def directive_to_dict(directive: RetryDirective) -> Dict[str, Any]:
    return {
        "should_retry": directive.should_retry,
        "mode": directive.mode,
        "modified_params": dict(directive.modified_params),
    }
