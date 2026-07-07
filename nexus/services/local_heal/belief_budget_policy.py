"""C6AC: Belief-based retry budget policy.

Resolves retry budget (max_rounds) from belief confidence and uncertainty.
Advisory only: cannot override verifier / claim / owner gate.
"""
from __future__ import annotations

from typing import Any


DEFAULT_MAX_ROUNDS = 2
MIN_ROUNDS = 1
MAX_ROUNDS = 4


def resolve_retry_budget(
    belief_before: float | None = None,
    uncertainty_delta: float | None = None,
) -> dict[str, Any]:
    """Resolve retry budget from belief confidence and uncertainty.

    Policy:
    - High confidence (>= 0.75) + low uncertainty (delta < 0): conservative (1 round)
    - Low confidence (< 0.4) + high uncertainty (delta >= 0.15): exploratory (3 rounds)
    - Otherwise: moderate (2 rounds)

    Always bounded [1, 4].
    Fail-open: returns moderate budget on missing/invalid input.
    """
    if belief_before is None or uncertainty_delta is None:
        return {
            "max_rounds": DEFAULT_MAX_ROUNDS,
            "policy": "moderate",
            "belief_before": belief_before,
            "uncertainty_delta": uncertainty_delta,
            "cannot_override_verifier": True,
        }

    try:
        b = float(belief_before)
        d = float(uncertainty_delta)
    except (TypeError, ValueError):
        return {
            "max_rounds": DEFAULT_MAX_ROUNDS,
            "policy": "moderate",
            "belief_before": belief_before,
            "uncertainty_delta": uncertainty_delta,
            "cannot_override_verifier": True,
        }

    if b >= 0.75 and d < 0:
        rounds = 1
        policy = "conservative"
    elif b < 0.4 and d >= 0.15:
        rounds = 3
        policy = "exploratory"
    else:
        rounds = 2
        policy = "moderate"

    rounds = max(MIN_ROUNDS, min(MAX_ROUNDS, rounds))

    return {
        "max_rounds": rounds,
        "policy": policy,
        "belief_before": b,
        "uncertainty_delta": d,
        "cannot_override_verifier": True,
    }
