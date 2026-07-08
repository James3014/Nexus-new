"""P6-C1: Rollout Candidate Policy Contract Tests."""
from __future__ import annotations

import json
import pytest
from nexus.services.local_heal.p6_rollout_policy import (
    P6RolloutPolicy,
    RolloutState,
    build_rollout_policy,
)


def test_all_rollout_states_accepted():
    """P6-C1: Each rollout_state is accepted."""
    for state in RolloutState:
        policy = build_rollout_policy(state, reason="test")
        assert policy.rollout_state == state.value


def test_unknown_rollout_state_raises():
    """P6-C1: Unknown rollout_state raises ValueError."""
    with pytest.raises(ValueError):
        build_rollout_policy("invalid_state")


def test_rollout_candidate_not_production():
    """P6-C1: rollout_candidate still has default_runtime_allowed=false."""
    policy = build_rollout_policy(RolloutState.ROLLOUT_CANDIDATE)
    assert policy.default_runtime_allowed is False


def test_rollout_candidate_not_public_claim():
    """P6-C1: rollout_candidate still has public_claim_allowed=false."""
    policy = build_rollout_policy(RolloutState.ROLLOUT_CANDIDATE)
    assert policy.public_claim_allowed is False


def test_rollout_candidate_not_production_ready():
    """P6-C1: rollout_candidate still has production_ready=false."""
    policy = build_rollout_policy(RolloutState.ROLLOUT_CANDIDATE)
    assert policy.production_ready is False


def test_verifier_required_all_states():
    """P6-C1: verifier_required=true for all states."""
    for state in RolloutState:
        policy = build_rollout_policy(state)
        assert policy.verifier_required is True


def test_claim_gate_required_all_states():
    """P6-C1: claim_gate_required=true for all states."""
    for state in RolloutState:
        policy = build_rollout_policy(state)
        assert policy.claim_gate_required is True


def test_memory_not_allowed_all_states():
    """P6-C1: memory_signal_allowed_for_quota=false for all states."""
    for state in RolloutState:
        policy = build_rollout_policy(state)
        assert policy.memory_signal_allowed_for_quota is False


def test_belief_not_allowed_all_states():
    """P6-C1: belief_signal_allowed_for_quota=false for all states."""
    for state in RolloutState:
        policy = build_rollout_policy(state)
        assert policy.belief_signal_allowed_for_quota is False


def test_p5_override_not_allowed():
    """P6-C1: p5_override_allowed=false for all states."""
    for state in RolloutState:
        policy = build_rollout_policy(state)
        assert policy.p5_override_allowed is False


def test_policy_json_serializable():
    """P6-C1: Policy is JSON-serializable."""
    policy = build_rollout_policy(RolloutState.ROLLOUT_CANDIDATE)
    d = {
        "policy_version": policy.policy_version,
        "rollout_state": policy.rollout_state,
        "default_runtime_allowed": policy.default_runtime_allowed,
    }
    json_str = json.dumps(d)
    assert len(json_str) > 0
