"""Unit tests for G5 Failure Behavior Matrix in Provider Adoption Framework."""

from nexus.calibration.provider_adoption.failure import (
    FailureClass,
    FailureObservationItem,
    build_failure_matrix,
    get_default_failure_contracts,
)


def test_failure_matrix_separation_of_contract_and_observation_fix_6_3():
    """Verify Invariant 6.3: expected contract is not reported as observed evidence."""
    fm = build_failure_matrix()
    # Contract asserts fail-closed expectations
    assert fm.all_fail_closed_contract is True

    # But without physical fault injection, observations must be NOT_EVALUATED
    assert fm.all_fail_closed_observed is None
    for fc in FailureClass:
        obs = fm.observations[fc.value]
        assert obs.exercised is False
        assert obs.observed_fail_closed is None
        assert obs.observed_retry_behavior == "NOT_EVALUATED"


def test_failure_matrix_physical_observation_recording():
    # Simulate exercising one fault
    obs = {
        fc.value: FailureObservationItem(
            failure_class=fc,
            exercised=(fc == FailureClass.AUTH_ERROR),
            observed_fail_closed=True if fc == FailureClass.AUTH_ERROR else None,
            observed_retry_behavior="ABORT_IMMEDIATELY"
            if fc == FailureClass.AUTH_ERROR
            else "NOT_EVALUATED",
            evidence_notes="Exercised in test",
        )
        for fc in FailureClass
    }
    fm = build_failure_matrix(observations=obs)
    # Since not all failure classes were exercised, overall observed is not True
    assert fm.all_fail_closed_observed is False
    assert fm.observations[FailureClass.AUTH_ERROR.value].observed_fail_closed is True


def test_retry_invariant_outcome_unknown_not_retry_permission():
    """Verify Invariant: timeout disallows blind retry without safe idempotency."""
    contracts = get_default_failure_contracts()
    timeout_contract = contracts[FailureClass.PROVIDER_TIMEOUT.value]
    assert timeout_contract.expected_fail_closed is True
    assert timeout_contract.retry_allowed is False
