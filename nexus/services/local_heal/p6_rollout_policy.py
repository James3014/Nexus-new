from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RolloutState(str, Enum):
    DISABLED = "disabled"
    ENV_GUARDED = "env_guarded"
    ROLLOUT_CANDIDATE = "rollout_candidate"
    BLOCKED = "blocked"
    ROLLBACK_REQUIRED = "rollback_required"


@dataclass(frozen=True)
class P6RolloutPolicy:
    policy_version: str = "1.0"
    rollout_state: str = "env_guarded"
    env_guard_required: bool = True
    default_runtime_allowed: bool = False
    runtime_route_mutation_allowed: bool = False
    public_claim_allowed: bool = False
    production_ready: bool = False
    verifier_required: bool = True
    claim_gate_required: bool = True
    memory_signal_allowed_for_quota: bool = False
    belief_signal_allowed_for_quota: bool = False
    p5_override_allowed: bool = False
    reason: str = ""


def build_rollout_policy(state: RolloutState, reason: str = "") -> P6RolloutPolicy:
    """Build a P6 rollout policy for the given state."""
    # All states share these hard rules
    base = {
        "policy_version": "1.0",
        "env_guard_required": True,
        "public_claim_allowed": False,
        "production_ready": False,
        "verifier_required": True,
        "claim_gate_required": True,
        "memory_signal_allowed_for_quota": False,
        "belief_signal_allowed_for_quota": False,
        "p5_override_allowed": False,
        "reason": reason,
    }

    if state == RolloutState.DISABLED:
        return P6RolloutPolicy(**base, rollout_state=state.value, default_runtime_allowed=False, runtime_route_mutation_allowed=False)
    elif state == RolloutState.ENV_GUARDED:
        return P6RolloutPolicy(**base, rollout_state=state.value, default_runtime_allowed=False, runtime_route_mutation_allowed=False)
    elif state == RolloutState.ROLLOUT_CANDIDATE:
        return P6RolloutPolicy(**base, rollout_state=state.value, default_runtime_allowed=False, runtime_route_mutation_allowed=False)
    elif state == RolloutState.BLOCKED:
        return P6RolloutPolicy(**base, rollout_state=state.value, default_runtime_allowed=False, runtime_route_mutation_allowed=False)
    elif state == RolloutState.ROLLBACK_REQUIRED:
        return P6RolloutPolicy(**base, rollout_state=state.value, default_runtime_allowed=False, runtime_route_mutation_allowed=False)
    else:
        raise ValueError(f"Unknown rollout_state: {state}")
