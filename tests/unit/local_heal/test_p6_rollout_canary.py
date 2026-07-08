"""P6-C4: Rollback / Canary Gate Simulator Tests."""
from __future__ import annotations

import json
import pytest
from nexus.services.local_heal.p6_rollout_policy import RolloutState, build_rollout_policy
from nexus.services.local_heal.p6_rollout_monitor import P6RolloutMetrics, compute_rollout_metrics
from nexus.services.local_heal.p6_rollout_canary import P6CanaryDecision, evaluate_canary_decision


def _make_metrics(total=24, unsafe=0, unknown_healthy=0, mem_override=0, verifier=1.0, claim=1.0, public=0, receipt=1.0, flag_off=1.0, constrained_min=3):
    return P6RolloutMetrics(
        total_rows=total,
        rows_per_arm={"p6_on_healthy": 3, "p6_on_constrained": 3},
        rows_per_arm_min=3,
        unsafe_action_count=unsafe,
        memory_or_belief_quota_override_count=mem_override,
        unknown_quota_as_healthy_count=unknown_healthy,
        verifier_required_rate=verifier,
        claim_gate_required_rate=claim,
        public_claim_allowed_count=public,
        receipt_complete_rate=receipt,
        flag_off_behavior_unchanged_rate=flag_off,
        constrained_candidate_count_min=constrained_min,
        rollout_candidate_gate_passed=True,
        blocked_reasons=[],
    )


def test_passing_metrics_allows_rollout():
    """P6-C4: Passing metrics allows rollout_candidate but not production."""
    policy = build_rollout_policy(RolloutState.ROLLOUT_CANDIDATE)
    metrics = _make_metrics()
    decision = evaluate_canary_decision(policy=policy, metrics=metrics)
    assert decision.decision == "allow_rollout_candidate"
    assert decision.default_runtime_allowed is False
    assert decision.public_claim_allowed is False
    assert decision.production_ready is False


def test_public_claim_always_false():
    """P6-C4: public_claim_allowed=false always."""
    policy = build_rollout_policy(RolloutState.ROLLOUT_CANDIDATE)
    metrics = _make_metrics()
    decision = evaluate_canary_decision(policy=policy, metrics=metrics)
    assert decision.public_claim_allowed is False


def test_insufficient_rows_continues_env_guarded():
    """P6-C4: Insufficient rows → continue_env_guarded."""
    policy = build_rollout_policy(RolloutState.ROLLOUT_CANDIDATE)
    metrics = P6RolloutMetrics(
        total_rows=10, rows_per_arm={"p6_on_healthy": 10}, rows_per_arm_min=10,
        unsafe_action_count=0, memory_or_belief_quota_override_count=0,
        unknown_quota_as_healthy_count=0, verifier_required_rate=1.0,
        claim_gate_required_rate=1.0, public_claim_allowed_count=0,
        receipt_complete_rate=1.0, flag_off_behavior_unchanged_rate=1.0,
        constrained_candidate_count_min=5, rollout_candidate_gate_passed=False,
        blocked_reasons=["insufficient_rows"],
    )
    decision = evaluate_canary_decision(policy=policy, metrics=metrics)
    assert decision.decision == "continue_env_guarded"
    assert decision.allow_rollout_candidate is False


def test_unsafe_action_triggers_rollback():
    """P6-C4: unsafe_action_count > 0 triggers rollback_required."""
    policy = build_rollout_policy(RolloutState.ROLLOUT_CANDIDATE)
    metrics = _make_metrics(unsafe=1)
    decision = evaluate_canary_decision(policy=policy, metrics=metrics)
    assert decision.decision == "rollback_required"
    assert decision.rollback_required is True


def test_verifier_rate_low_triggers_rollback():
    """P6-C4: verifier_required_rate < 100 triggers rollback_required."""
    policy = build_rollout_policy(RolloutState.ROLLOUT_CANDIDATE)
    metrics = _make_metrics(verifier=0.5)
    decision = evaluate_canary_decision(policy=policy, metrics=metrics)
    assert decision.decision == "rollback_required"
    assert decision.rollback_required is True


def test_memory_override_blocks_canary():
    """P6-C4: memory/belief override blocks canary."""
    policy = build_rollout_policy(RolloutState.ROLLOUT_CANDIDATE)
    metrics = P6RolloutMetrics(
        total_rows=24, rows_per_arm={"p6_on_healthy": 24}, rows_per_arm_min=24,
        unsafe_action_count=0, memory_or_belief_quota_override_count=1,
        unknown_quota_as_healthy_count=0, verifier_required_rate=1.0,
        claim_gate_required_rate=1.0, public_claim_allowed_count=0,
        receipt_complete_rate=1.0, flag_off_behavior_unchanged_rate=1.0,
        constrained_candidate_count_min=5, rollout_candidate_gate_passed=True,
        blocked_reasons=[],
    )
    decision = evaluate_canary_decision(policy=policy, metrics=metrics)
    assert decision.allow_rollout_candidate is False
    assert "memory_belief_quota_override" in decision.reasons


def test_default_runtime_allowed_always_false():
    """P6-C4: default_runtime_allowed=false always."""
    policy = build_rollout_policy(RolloutState.ROLLOUT_CANDIDATE)
    metrics = _make_metrics()
    decision = evaluate_canary_decision(policy=policy, metrics=metrics)
    assert decision.default_runtime_allowed is False


def test_production_ready_always_false():
    """P6-C4: production_ready=false always."""
    policy = build_rollout_policy(RolloutState.ROLLOUT_CANDIDATE)
    metrics = _make_metrics()
    decision = evaluate_canary_decision(policy=policy, metrics=metrics)
    assert decision.production_ready is False


def test_json_serializable():
    """P6-C4: Decision is JSON-serializable."""
    policy = build_rollout_policy(RolloutState.ROLLOUT_CANDIDATE)
    metrics = _make_metrics()
    decision = evaluate_canary_decision(policy=policy, metrics=metrics)
    d = {
        "decision": decision.decision,
        "rollback_required": decision.rollback_required,
        "public_claim_allowed": decision.public_claim_allowed,
    }
    json_str = json.dumps(d)
    assert len(json_str) > 0
