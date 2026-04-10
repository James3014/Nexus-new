from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple


from .learning_evidence import LearningEvidence
from .learning_governance import LearningGovernance
from .state_contracts import NexusState


class LearningScorer:
    """Derive measurable C-phase learning signals from execution evidence."""

    HISTORY_WINDOW = 10

    @classmethod
    def apply(cls, state: NexusState, evidence: LearningEvidence) -> None:
        metadata = state.metadata
        metadata["episode_count"] = int(metadata.get("episode_count", 0)) + 1
        decision = LearningGovernance.evaluate(state, evidence)
        if decision.freeze_learning:
            return

        pattern_reuse = cls._compute_pattern_reuse(evidence)
        lesson_quality = cls._compute_lesson_quality(evidence)

        # Next-run hit rate: rolling success history blended with reuse signal.
        window = cls._update_success_window(metadata, evidence.success)
        success_rate = (sum(window) / len(window)) * 100.0 if window else 0.0
        next_run_hit_rate = cls._compute_next_run_hit_rate(success_rate, pattern_reuse)

        metadata["pattern_reuse_rate"] = max(
            float(metadata.get("pattern_reuse_rate", 0.0)),
            float(pattern_reuse),
        )
        metadata["lesson_quality"] = max(
            float(metadata.get("lesson_quality", 0.0)),
            float(lesson_quality),
        )
        metadata["next_run_hit_rate"] = max(
            float(metadata.get("next_run_hit_rate", 0.0)),
            float(next_run_hit_rate),
        )

    @classmethod
    def _update_success_window(cls, metadata: dict, success: bool) -> List[int]:
        raw = metadata.get("learning_success_window")
        window: List[int] = []
        if isinstance(raw, list):
            for item in raw:
                try:
                    window.append(1 if int(item) > 0 else 0)
                except (TypeError, ValueError):
                    continue
        window.append(1 if success else 0)
        window = window[-cls.HISTORY_WINDOW :]
        metadata["learning_success_window"] = window
        return window

    @staticmethod
    def _compute_pattern_reuse(evidence: LearningEvidence) -> float:
        # 🧪 [v24.0 Evolution] Bayesian Adaptive Scoring
        # High aggression (e.g., 0.9) favors exploration (coverage bonus)
        # Low aggression (e.g., 0.1) favors precision (success bonus)
        exploration_weight = 0.5 + (evidence.bayesian_aggression * 0.5) # 0.5 to 0.95
        precision_weight = 1.5 - (evidence.bayesian_aggression * 0.5)   # 1.45 to 1.05

        coverage_bonus = min(20.0, (evidence.unique_phase_count / 6.0) * 20.0) * exploration_weight
        hit_bonus = min(25.0, float(evidence.policy_hit_count) * 10.0)
        success_bonus = (15.0 if evidence.success else 0.0) * precision_weight
        retry_penalty = min(25.0, float(evidence.retry_count) * 8.0)
        
        score = 45.0 + coverage_bonus + hit_bonus + success_bonus - retry_penalty
        return max(0.0, min(100.0, score))

    @staticmethod
    def _compute_lesson_quality(evidence: LearningEvidence) -> float:
        # 🧪 [v24.0 Evolution] Entropy-Aware Quality Penalty
        # High cognitive entropy (chaos, escalations, vetos) drastically reduces lesson quality
        entropy_penalty = min(40.0, evidence.entropy_score * 0.8)

        phase_coverage = min(100.0, (evidence.unique_phase_count / 6.0) * 100.0)
        retry_penalty = min(80.0, evidence.retry_count * 15.0)
        stability = max(0.0, 100.0 - retry_penalty - entropy_penalty) # Subtracted entropy
        
        lesson_quality = (phase_coverage * 0.55) + (stability * 0.45)
        lesson_quality += 10.0 if evidence.success else -10.0
        
        # Lower the floor if entropy was high, else keep it stable
        floor_score = max(40.0, 88.0 - entropy_penalty) if evidence.success else 65.0
        lesson_quality = max(lesson_quality, floor_score)
        
        return max(0.0, min(100.0, lesson_quality))

    @staticmethod
    def _compute_next_run_hit_rate(success_rate: float, pattern_reuse: float) -> float:
        return min(100.0, (success_rate * 0.7) + (pattern_reuse * 0.3))
