"""Unit tests for Lifecycle State Machine and Stop Condition Enforcement (Fix 6.4)."""

import pytest

from nexus.calibration.provider_adoption.contracts import StopConditions
from nexus.calibration.provider_adoption.state_machine import (
    LifecycleState,
    LifecycleStateMachine,
)


def test_valid_sequential_transitions():
    sm = LifecycleStateMachine("EXP-TEST")
    assert sm.current_state == LifecycleState.DRAFT

    sm.transition_to(LifecycleState.CONTRACT_FROZEN, "G0")
    assert sm.current_state == LifecycleState.CONTRACT_FROZEN

    sm.transition_to(LifecycleState.IDENTITY_INSPECTED, "G1")
    assert sm.current_state == LifecycleState.IDENTITY_INSPECTED

    sm.transition_to(LifecycleState.CAPABILITY_PROBED, "G2")
    assert sm.current_state == LifecycleState.CAPABILITY_PROBED

    sm.transition_to(LifecycleState.COHORT_EVALUATED, "G3")
    assert sm.current_state == LifecycleState.COHORT_EVALUATED

    sm.transition_to(LifecycleState.OPERATIONAL_EVALUATED, "G4")
    assert sm.current_state == LifecycleState.OPERATIONAL_EVALUATED

    sm.transition_to(LifecycleState.FAILURE_EVALUATED, "G5")
    assert sm.current_state == LifecycleState.FAILURE_EVALUATED

    sm.transition_to(LifecycleState.RECOMMENDATION_READY, "G6")
    assert sm.current_state == LifecycleState.RECOMMENDATION_READY


def test_invalid_lifecycle_transition_fails_closed():
    sm = LifecycleStateMachine("EXP-TEST")
    # Cannot jump directly from DRAFT to RECOMMENDATION_READY
    with pytest.raises(ValueError, match="INVALID_LIFECYCLE_TRANSITION"):
        sm.transition_to(LifecycleState.RECOMMENDATION_READY)


def test_stop_condition_consecutive_failures_enforcement_fix_6_4():
    """Verify Invariant 6.4: consecutive failures trigger STOPPED_BY_CONDITION."""
    sm = LifecycleStateMachine("EXP-TEST")
    sc = StopConditions(
        max_consecutive_failures=3, max_error_rate=0.5, safety_abort_on_timeout=True
    )

    # 2 consecutive failures: does not trigger
    stop, reason = sm.check_stop_conditions(
        sc, consecutive_failures=2, total_failures=2, total_executed=2
    )
    assert not stop

    # 3 consecutive failures: triggers stop
    stop, reason = sm.check_stop_conditions(
        sc, consecutive_failures=3, total_failures=3, total_executed=3
    )
    assert stop
    assert "consecutive failures" in reason


def test_stop_condition_timeout_safety_abort():
    sm = LifecycleStateMachine("EXP-TEST")
    sc = StopConditions(
        max_consecutive_failures=5, max_error_rate=0.5, safety_abort_on_timeout=True
    )

    stop, reason = sm.check_stop_conditions(
        sc,
        consecutive_failures=1,
        total_failures=1,
        total_executed=1,
        timed_out=True,
    )
    assert stop
    assert "timeout" in reason.lower()
