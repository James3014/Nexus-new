from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .learning_evidence import LearningEvidence
from .state_contracts import NexusState


@dataclass(frozen=True)
class GovernanceProfile:
    alpha: float = 1.0
    beta: float = 1.0
    gamma: float = 1.0
    token_budget: float = 5000.0
    memory_health_baseline: float = 100.0
    valid_proof_types: frozenset[str] = frozenset({"git_diff", "git_diff_checksum", "checksum"})


@dataclass(frozen=True)
class LearningDecision:
    freeze_learning: bool
    curiosity_score: float
    reasons: List[str]
    action: str


class LearningSteward:
    """Single governance entrypoint for C-phase learning decisions."""

    def __init__(self, profile: GovernanceProfile | None = None) -> None:
        self.profile = profile or GovernanceProfile()

    def decide(self, state: NexusState, evidence: LearningEvidence) -> LearningDecision:
        reasons: List[str] = []
        freeze = False
        metadata = state.metadata

        if self._requires_physical_proof(evidence):
            if not evidence.proof_present:
                freeze = True
                reasons.append("missing_physical_proof_evidence")
            elif evidence.proof_type.lower() not in self.profile.valid_proof_types:
                freeze = True
                reasons.append("invalid_physical_proof_type")

        if bool(metadata.get("sir_veto_learning", False)):
            freeze = True
            reasons.append("sir_veto")

        novelty = self._novelty(evidence)
        failure_history = self._failure_history(metadata)
        feedback_reward = self._feedback_reward(state)
        curiosity_score = (
            (self.profile.alpha * novelty)
            + (self.profile.gamma * feedback_reward)
            - (self.profile.beta * failure_history)
        )
        if curiosity_score < 0.0:
            freeze = True
            reasons.append("curiosity_negative")

        if float(state.total_token_usage or 0.0) > self.profile.token_budget:
            freeze = True
            reasons.append("token_budget_exceeded")

        canary_reasons = self._evaluate_canary(metadata)
        if canary_reasons:
            freeze = True
            reasons.extend(canary_reasons)

        metadata["curiosity_score"] = round(curiosity_score, 2)
        metadata["curiosity_novelty"] = round(novelty, 2)
        metadata["curiosity_failure_penalty"] = round(failure_history, 2)
        metadata["curiosity_feedback_reward"] = round(feedback_reward, 2)
        metadata["learning_frozen"] = freeze
        metadata["learning_freeze_reasons"] = reasons

        action = "FREEZE" if freeze else ("INGEST" if evidence.success else "DISCARD")
        return LearningDecision(
            freeze_learning=freeze,
            curiosity_score=round(curiosity_score, 2),
            reasons=reasons,
            action=action,
        )

    @staticmethod
    def _requires_physical_proof(evidence: LearningEvidence) -> bool:
        return bool(evidence.success and evidence.patch_generated and evidence.patch_apply_success)

    @staticmethod
    def _novelty(evidence: LearningEvidence) -> float:
        coverage_ratio = min(1.0, evidence.unique_phase_count / 6.0)
        hit_density = min(1.0, evidence.policy_hit_count / 5.0)
        return round((coverage_ratio * 70.0) + (hit_density * 30.0), 2)

    @staticmethod
    def _failure_history(metadata: dict) -> float:
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

    @staticmethod
    def _feedback_reward(state: NexusState) -> float:
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
        conflict = (pipeline_success is True and review_is_negative) or (pipeline_success is False and review_is_positive)
        if not conflict:
            if review_is_positive:
                reward += 20.0
            elif review_is_negative:
                reward -= 25.0
        include_ci_signal = pipeline_success is None or bool(metadata.get("use_test_pass_rate_for_curiosity", False))
        if include_ci_signal:
            reward += (test_pass_rate - 0.5) * 40.0
        return round(max(-60.0, min(60.0, reward)), 2)

    def _evaluate_canary(self, metadata: dict) -> List[str]:
        baseline = float(metadata.get("memory_health_baseline", self.profile.memory_health_baseline))
        current = float(metadata.get("memory_health_current", baseline))
        if baseline <= 0:
            return []
        drop_pct = ((baseline - current) / baseline) * 100.0
        if drop_pct > 10.0:
            metadata["canary_alert"] = True
            return ["memory_health_drop"]
        ntr = float(metadata.get("negative_transfer_rate", 0.0))
        if ntr > 5.0:
            metadata["canary_alert"] = True
            return ["ntr_high"]
        metadata["canary_alert"] = False
        return []
