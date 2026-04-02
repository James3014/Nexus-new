from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple

from dataclasses import dataclass

from .learning_evidence import LearningEvidence
from .state_contracts import NexusState


@dataclass(frozen=True)
class LearningDecision:
    freeze_learning: bool
    curiosity_score: float
    reasons: List[str]


class LearningGovernance:
    """Guardrails for exploratory learning updates."""

    ALPHA = 1.0
    BETA = 1.0
    GAMMA = 1.0
    DEFAULT_TOKEN_BUDGET = 5000
    DEFAULT_MEMORY_HEALTH_BASELINE = 100.0
    VALID_PROOF_TYPES = {"git_diff", "git_diff_checksum", "checksum"}

    @classmethod
    def evaluate(cls, state: NexusState, evidence: LearningEvidence) -> LearningDecision:
        reasons: List[str] = []
        freeze = False
        metadata = state.metadata

        if cls._requires_physical_proof(evidence):
            if not evidence.proof_present:
                freeze = True
                reasons.append("missing_physical_proof_evidence")
            elif evidence.proof_type.lower() not in cls.VALID_PROOF_TYPES:
                freeze = True
                reasons.append("invalid_physical_proof_type")

        if bool(metadata.get("sir_veto_learning", False)):
            freeze = True
            reasons.append("sir_veto")

        novelty = cls._novelty(evidence)
        failure_history = cls._failure_history(metadata)
        feedback_reward = cls._feedback_reward(state)
        curiosity_score = (
            (cls.ALPHA * novelty)
            + (cls.GAMMA * feedback_reward)
            - (cls.BETA * failure_history)
        )
        if curiosity_score < 0.0:
            freeze = True
            reasons.append("curiosity_negative")

        token_budget = float(metadata.get("curiosity_token_budget", cls.DEFAULT_TOKEN_BUDGET))
        if float(state.total_token_usage or 0.0) > token_budget:
            freeze = True
            reasons.append("token_budget_exceeded")

        canary_reasons = cls._evaluate_canary(metadata)
        if canary_reasons:
            freeze = True
            reasons.extend(canary_reasons)

        metadata["curiosity_score"] = round(curiosity_score, 2)
        metadata["curiosity_novelty"] = round(novelty, 2)
        metadata["curiosity_failure_penalty"] = round(failure_history, 2)
        metadata["curiosity_feedback_reward"] = round(feedback_reward, 2)
        metadata["learning_frozen"] = freeze
        metadata["learning_freeze_reasons"] = reasons

        return LearningDecision(
            freeze_learning=freeze,
            curiosity_score=round(curiosity_score, 2),
            reasons=reasons,
        )

    @staticmethod
    def _requires_physical_proof(evidence: LearningEvidence) -> bool:
        return bool(
            evidence.success
            and evidence.patch_generated
            and evidence.patch_apply_success
        )

    @classmethod
    def _novelty(cls, evidence: LearningEvidence) -> float:
        coverage_ratio = min(1.0, evidence.unique_phase_count / 6.0)
        hit_density = min(1.0, evidence.policy_hit_count / 5.0)
        return round((coverage_ratio * 70.0) + (hit_density * 30.0), 2)

    @classmethod
    def _failure_history(cls, metadata: dict) -> float:
        raw = metadata.get("learning_success_window")
        if not isinstance(raw, list) or not raw:
            return 0.0
        values: List[int] = []
        for item in raw:
            try:
                values.append(1 if int(item) > 0 else 0)
            except (TypeError, ValueError):
                continue
        if not values:
            return 0.0
        failure_rate = 1.0 - (sum(values) / len(values))
        return round(failure_rate * 100.0, 2)

    @classmethod
    def _feedback_reward(cls, state: NexusState) -> float:
        metadata = state.metadata
        review_status = str(metadata.get("last_review_status", "")).upper()
        test_pass_rate = float(state.health_metrics.test_pass_rate or 0.0)
        pipeline_success = metadata.get("pipeline_success")

        reward = 0.0

        if pipeline_success is True:
            reward += 15.0
        elif pipeline_success is False:
            reward -= 15.0

        review_is_positive = review_status in {"APPROVED", "PASS"}
        review_is_negative = review_status in {"REJECTED", "FAILED"}
        review_conflicts_with_pipeline = (
            (pipeline_success is True and review_is_negative)
            or (pipeline_success is False and review_is_positive)
        )
        if not review_conflicts_with_pipeline:
            if review_is_positive:
                reward += 20.0
            elif review_is_negative:
                reward -= 25.0

        # CI score is only applied when pipeline_success is unknown, or caller
        # explicitly asks to include this signal to avoid stale-default penalties.
        include_ci_signal = pipeline_success is None or bool(
            metadata.get("use_test_pass_rate_for_curiosity", False)
        )
        if include_ci_signal:
            # Normalize CI signal to [-20, +20] by centering pass rate at 0.5.
            reward += (test_pass_rate - 0.5) * 40.0

        return round(max(-60.0, min(60.0, reward)), 2)

    @classmethod
    def _evaluate_canary(cls, metadata: dict) -> List[str]:
        reasons: List[str] = []
        baseline = float(metadata.get("memory_health_baseline", cls.DEFAULT_MEMORY_HEALTH_BASELINE))
        current = float(metadata.get("memory_health_current", baseline))
        if baseline > 0:
            drop_pct = ((baseline - current) / baseline) * 100.0
            if drop_pct > 10.0:
                metadata["canary_alert"] = True
                reasons.append("memory_health_drop")
        ntr = float(metadata.get("negative_transfer_rate", 0.0))
        if ntr > 5.0:
            metadata["canary_alert"] = True
            reasons.append("ntr_high")
        return reasons
