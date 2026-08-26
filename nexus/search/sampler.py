from typing import Any, Dict, List, Protocol, Sequence

from nexus.search.contracts import RetryDirective
from nexus.search.diversity import DiversityMeter


class VerifierSignalLike(Protocol):
    """Minimal verifier feedback surface read by the sampler."""

    passed: bool
    failure_tags: Sequence[str]
    verifier_name: str


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
                           verdicts: Sequence[VerifierSignalLike] | None = None) -> RetryDirective:
        
        diversity_score = self.meter.compute_diversity(candidate_contents)
        feedback = _route_failure(verdicts or [])
        
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


def _route_failure(verdicts: Sequence[VerifierSignalLike]) -> Dict[str, Any]:
    """Map failed verifier signals to bounded search retry hints."""
    hints = []
    strategies = []

    for v in verdicts:
        if not v.passed:
            tags = " ".join(getattr(v, "failure_tags", []) or [])
            if "MISSING:" in tags or "UNDEFINED" in tags:
                hints.append("IMPORT_AWARE_FIX")
                strategies.append("include_common_imports")
            if "INHERITANCE" in getattr(v, "verifier_name", "").upper():
                hints.append("HIERARCHY_PRESERVING")
                strategies.append("analyze_mro_first")

    return {
        "retry_hints": list(dict.fromkeys(hints)),
        "suggested_strategies": list(dict.fromkeys(strategies)),
        "feedback_loop_active": len(hints) > 0,
    }
