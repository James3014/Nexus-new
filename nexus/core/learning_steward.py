from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, List

from .learning_evidence import LearningEvidence
from .state_contracts import NexusState
from nexus.engine.openseeker_alignment import MIN_EVOLUTION_STEPS


@dataclass(frozen=True)
class GovernanceProfile:
    alpha: float = 1.0
    beta: float = 1.0
    gamma: float = 1.0
    token_budget: float = 5000.0
    memory_health_baseline: float = 100.0
    min_evolution_steps: int = MIN_EVOLUTION_STEPS
    valid_proof_types: frozenset[str] = frozenset({"git_diff", "git_diff_checksum", "checksum"})


@dataclass(frozen=True)
class LearningDecision:
    freeze_learning: bool
    curiosity_score: float
    reasons: List[str]
    action: str


@dataclass(frozen=True)
class LearningPathDecision:
    nexus_action: str
    model_action: str
    reasons: List[str]
    promotion_ready: bool
    export_ready: bool


class LearningSteward:
    """Single governance entrypoint for C-phase learning decisions."""

    def __init__(self, profile: GovernanceProfile | None = None) -> None:
        self.profile = profile or GovernanceProfile()

    def decide(self, state: NexusState, evidence: LearningEvidence) -> LearningDecision:
        reasons: List[str] = []
        freeze = False
        metadata = state.metadata
        profile = self._profile_for(metadata)

        if self._requires_physical_proof(evidence):
            if not evidence.proof_present:
                freeze = True
                reasons.append("missing_physical_proof_evidence")
            elif evidence.proof_type.lower() not in profile.valid_proof_types:
                freeze = True
                reasons.append("invalid_physical_proof_type")

        if bool(metadata.get("sir_veto_learning", False)):
            freeze = True
            reasons.append("sir_veto")

        novelty = self._novelty(evidence)
        failure_history = self._failure_history(metadata)
        feedback_reward = self._feedback_reward(state)
        curiosity_score = (
            (profile.alpha * novelty)
            + (profile.gamma * feedback_reward)
            - (profile.beta * failure_history)
        )
        if curiosity_score < 0.0:
            freeze = True
            reasons.append("curiosity_negative")

        if float(state.total_token_usage or 0.0) > profile.token_budget:
            freeze = True
            reasons.append("token_budget_exceeded")

        canary_reasons = self._evaluate_canary(metadata, profile)
        if canary_reasons:
            freeze = True
            reasons.extend(canary_reasons)

        trajectory_steps = int(evidence.trajectory_step_count or len(evidence.phases))
        low_step_filtered = bool(evidence.success and trajectory_steps < profile.min_evolution_steps)
        if low_step_filtered:
            freeze = True
            reasons.append("low_step_trajectory")

        metadata["curiosity_score"] = round(curiosity_score, 2)
        metadata["curiosity_novelty"] = round(novelty, 2)
        metadata["curiosity_failure_penalty"] = round(failure_history, 2)
        metadata["curiosity_feedback_reward"] = round(feedback_reward, 2)
        metadata["learning_frozen"] = freeze
        metadata["learning_freeze_reasons"] = reasons
        metadata["min_evolution_steps"] = profile.min_evolution_steps
        metadata["trajectory_step_count"] = trajectory_steps
        metadata["low_step_filtered"] = low_step_filtered

        action = "FREEZE" if freeze else ("INGEST" if evidence.success else "DISCARD")
        metadata["learning_action"] = action
        return LearningDecision(
            freeze_learning=freeze,
            curiosity_score=round(curiosity_score, 2),
            reasons=reasons,
            action=action,
        )

    def decide_experience(self, experience: Any) -> LearningPathDecision:
        """Split Nexus policy learning from model-training export decisions."""
        if not experience:
            return LearningPathDecision(
                nexus_action="DISCARD",
                model_action="DISCARD",
                reasons=["missing_experience"],
                promotion_ready=False,
                export_ready=False,
            )

        reasons: List[str] = []
        outcome = str(self._get(experience, "outcome", ""))
        if outcome != "verified_success":
            return LearningPathDecision(
                nexus_action="FREEZE",
                model_action="FREEZE",
                reasons=["outcome_not_verified_success"],
                promotion_ready=False,
                export_ready=False,
            )

        gate_chain = self._get(experience, "gate_chain", {}) or {}
        missing_gates = [
            gate
            for gate in ("artifact", "claim", "delivery")
            if str(gate_chain.get(gate, "")) != "pass"
        ]
        if missing_gates:
            return LearningPathDecision(
                nexus_action="FREEZE",
                model_action="FREEZE",
                reasons=[f"missing_gate:{gate}" for gate in missing_gates],
                promotion_ready=False,
                export_ready=False,
            )

        lifecycle = list(self._get(experience, "capability_lifecycle", ()) or ())
        funnel_complete = any(bool(self._get(item, "funnel_complete", False)) for item in lifecycle)
        if not funnel_complete:
            reasons.append("no_complete_capability_funnel")

        s2t_refs = tuple(self._get(experience, "s2t_trace_refs", ()) or ())
        promotion_ready = funnel_complete
        export_ready = bool(s2t_refs)
        nexus_action = "PROMOTE_NEXUS" if promotion_ready else "INGEST_SHADOW"
        model_action = "EXPORT_MODEL" if export_ready else "INGEST_SHADOW"
        if not export_ready:
            reasons.append("missing_s2t_trace_refs")
        return LearningPathDecision(
            nexus_action=nexus_action,
            model_action=model_action,
            reasons=reasons,
            promotion_ready=promotion_ready,
            export_ready=export_ready,
        )

    def _profile_for(self, metadata: dict) -> GovernanceProfile:
        raw = metadata.get("governance_profile")
        if not isinstance(raw, dict):
            metadata["governance_profile_source"] = "default"
            return self.profile
        allowed: dict[str, float | int] = {}
        for key in ("alpha", "beta", "gamma", "token_budget", "memory_health_baseline"):
            if key in raw:
                try:
                    allowed[key] = float(raw[key])
                except (TypeError, ValueError):
                    metadata["governance_profile_source"] = "invalid_metadata_override"
                    return self.profile
        if "min_evolution_steps" in raw:
            try:
                allowed["min_evolution_steps"] = max(1, int(raw["min_evolution_steps"]))
            except (TypeError, ValueError):
                metadata["governance_profile_source"] = "invalid_metadata_override"
                return self.profile
        metadata["governance_profile_source"] = "metadata_override" if allowed else "default"
        return replace(self.profile, **allowed) if allowed else self.profile

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

    @staticmethod
    def _get(obj: Any, key: str, default: Any = None) -> Any:
        if isinstance(obj, dict):
            if key == "funnel_complete":
                return obj.get("funnel_complete", default)
            return obj.get(key, default)
        return getattr(obj, key, default)

    def _evaluate_canary(self, metadata: dict, profile: GovernanceProfile) -> List[str]:
        baseline = float(metadata.get("memory_health_baseline", profile.memory_health_baseline))
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
