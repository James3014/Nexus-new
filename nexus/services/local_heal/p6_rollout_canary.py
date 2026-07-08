from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nexus.services.local_heal.p6_rollout_policy import P6RolloutPolicy, RolloutState, build_rollout_policy
from nexus.services.local_heal.p6_rollout_monitor import P6RolloutMetrics, compute_rollout_metrics


@dataclass(frozen=True)
class P6CanaryDecision:
    canary_decision_version: str = "1.0"
    input_rollout_state: str = "env_guarded"
    metrics_gate_passed: bool = False
    decision: str = "continue_env_guarded"
    rollback_required: bool = False
    pause_required: bool = False
    continue_env_guarded: bool = False
    allow_rollout_candidate: bool = False
    default_runtime_allowed: bool = False
    public_claim_allowed: bool = False
    production_ready: bool = False
    reasons: list[str] = field(default_factory=list)


def evaluate_canary_decision(
    *,
    policy: P6RolloutPolicy,
    metrics: P6RolloutMetrics,
) -> P6CanaryDecision:
    """Evaluate canary decision from policy + metrics."""
    reasons = []
    rollback = False

    # Check severe violations → rollback
    if metrics.unsafe_action_count > 0:
        reasons.append("unsafe_action_detected")
        rollback = True
    if metrics.public_claim_allowed_count > 0:
        reasons.append("public_claim_allowed_detected")
        rollback = True
    if metrics.verifier_required_rate < 1.0:
        reasons.append("verifier_required_rate_incomplete")
        rollback = True
    if metrics.claim_gate_required_rate < 1.0:
        reasons.append("claim_gate_required_rate_incomplete")
        rollback = True
    if metrics.unknown_quota_as_healthy_count > 0:
        reasons.append("unknown_quota_treated_as_healthy")
        rollback = True

    # Check memory/belief override
    if metrics.memory_or_belief_quota_override_count > 0:
        reasons.append("memory_belief_quota_override")
        rollback = True

    # Check evidence sufficiency
    if metrics.total_rows < 24:
        reasons.append("insufficient_rows")
    if metrics.rows_per_arm_min < 3:
        reasons.append("insufficient_rows_per_arm")

    # Decision logic
    if rollback:
        decision = "rollback_required"
    elif metrics.rollout_candidate_gate_passed and policy.rollout_state == "rollout_candidate":
        decision = "allow_rollout_candidate"
    elif metrics.total_rows < 24:
        decision = "continue_env_guarded"
    else:
        decision = "pause_canary"

    return P6CanaryDecision(
        input_rollout_state=policy.rollout_state,
        metrics_gate_passed=metrics.rollout_candidate_gate_passed,
        decision=decision,
        rollback_required=rollback,
        pause_required=decision == "pause_canary",
        continue_env_guarded=decision == "continue_env_guarded",
        allow_rollout_candidate=decision == "allow_rollout_candidate",
        default_runtime_allowed=False,
        public_claim_allowed=False,
        production_ready=False,
        reasons=reasons,
    )
