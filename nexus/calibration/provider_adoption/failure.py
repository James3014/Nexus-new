"""G5 Failure Behavior Matrix module for Provider Adoption Experiments.

Schema: nexus.provider_experiment.failure_matrix.v1
Defines canonical failure taxonomy, expected failure contracts, and physical
failure observations.

False-Green Defense (Invariant 6.3):
- Expected failure behavior (failure_contract) is strictly separated from observed failure evidence (failure_observation).
- Expected contract definitions MUST NOT be reported as candidate evidence.
- Without physical fault injection or live observed failures, observation status remains NOT_EVALUATED.
- all_fail_closed_observed is None or False unless EVERY failure class was physically exercised and confirmed fail-closed.
- Invariant: OUTCOME_UNKNOWN != RETRY_PERMISSION. If outcome is unknown, retry is forbidden without safe idempotency proof.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

FAILURE_MATRIX_SCHEMA = "nexus.provider_experiment.failure_matrix.v1"


class FailureClass(str, Enum):
    AUTH_ERROR = "AUTH_ERROR"
    RATE_LIMIT = "RATE_LIMIT"
    PROVIDER_TIMEOUT = "PROVIDER_TIMEOUT"
    PROCESS_CRASH = "PROCESS_CRASH"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    SCHEMA_VIOLATION = "SCHEMA_VIOLATION"
    CONTEXT_OVERFLOW = "CONTEXT_OVERFLOW"
    NETWORK_FAILURE = "NETWORK_FAILURE"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


@dataclass(frozen=True)
class FailureContractItem:
    """Expected fail-closed behavior specification."""

    failure_class: FailureClass
    expected_fail_closed: bool
    retry_allowed: bool
    expected_action: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "failure_class": self.failure_class.value,
            "expected_fail_closed": self.expected_fail_closed,
            "retry_allowed": self.retry_allowed,
            "expected_action": self.expected_action,
        }


@dataclass(frozen=True)
class FailureObservationItem:
    """Actual observed evidence from physical fault injection or live execution."""

    failure_class: FailureClass
    exercised: bool
    observed_fail_closed: bool | None
    observed_retry_behavior: str
    evidence_notes: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "failure_class": self.failure_class.value,
            "exercised": self.exercised,
            "observed_fail_closed": self.observed_fail_closed,
            "observed_retry_behavior": self.observed_retry_behavior,
            "evidence_notes": self.evidence_notes,
        }


@dataclass(frozen=True)
class FailureMatrix:
    schema: str
    contracts: dict[str, FailureContractItem]
    observations: dict[str, FailureObservationItem]
    all_fail_closed_contract: bool
    all_fail_closed_observed: bool | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "contracts": {k: v.to_dict() for k, v in self.contracts.items()},
            "observations": {k: v.to_dict() for k, v in self.observations.items()},
            "all_fail_closed_contract": self.all_fail_closed_contract,
            "all_fail_closed_observed": self.all_fail_closed_observed,
        }


def get_default_failure_contracts() -> dict[str, FailureContractItem]:
    """Canonical fail-closed contract rules for candidate evaluation."""
    return {
        FailureClass.AUTH_ERROR.value: FailureContractItem(
            failure_class=FailureClass.AUTH_ERROR,
            expected_fail_closed=True,
            retry_allowed=False,
            expected_action="ABORT_IMMEDIATELY",
        ),
        FailureClass.RATE_LIMIT.value: FailureContractItem(
            failure_class=FailureClass.RATE_LIMIT,
            expected_fail_closed=True,
            retry_allowed=True,
            expected_action="BACKOFF_RETRY",
        ),
        FailureClass.PROVIDER_TIMEOUT.value: FailureContractItem(
            failure_class=FailureClass.PROVIDER_TIMEOUT,
            expected_fail_closed=True,
            retry_allowed=False,  # Invariant: OUTCOME_UNKNOWN != RETRY_PERMISSION
            expected_action="RECORD_TIMEOUT_ABORT",
        ),
        FailureClass.PROCESS_CRASH.value: FailureContractItem(
            failure_class=FailureClass.PROCESS_CRASH,
            expected_fail_closed=True,
            retry_allowed=False,
            expected_action="ISOLATE_PROCESS",
        ),
        FailureClass.INVALID_RESPONSE.value: FailureContractItem(
            failure_class=FailureClass.INVALID_RESPONSE,
            expected_fail_closed=True,
            retry_allowed=False,
            expected_action="REJECT_OUTPUT",
        ),
        FailureClass.SCHEMA_VIOLATION.value: FailureContractItem(
            failure_class=FailureClass.SCHEMA_VIOLATION,
            expected_fail_closed=True,
            retry_allowed=False,
            expected_action="REJECT_OUTPUT",
        ),
        FailureClass.CONTEXT_OVERFLOW.value: FailureContractItem(
            failure_class=FailureClass.CONTEXT_OVERFLOW,
            expected_fail_closed=True,
            retry_allowed=False,
            expected_action="REJECT_INPUT",
        ),
        FailureClass.NETWORK_FAILURE.value: FailureContractItem(
            failure_class=FailureClass.NETWORK_FAILURE,
            expected_fail_closed=True,
            retry_allowed=False,
            expected_action="ABORT_NETWORK_DEPENDENCY",
        ),
        FailureClass.PERMISSION_DENIED.value: FailureContractItem(
            failure_class=FailureClass.PERMISSION_DENIED,
            expected_fail_closed=True,
            retry_allowed=False,
            expected_action="TERMINATE_UNPRIVILEGED",
        ),
        FailureClass.INTERNAL_ERROR.value: FailureContractItem(
            failure_class=FailureClass.INTERNAL_ERROR,
            expected_fail_closed=True,
            retry_allowed=False,
            expected_action="REPORT_DEFECT",
        ),
    }


def create_initial_failure_observations() -> dict[str, FailureObservationItem]:
    """Create unexercised observation items."""
    return {
        fc.value: FailureObservationItem(
            failure_class=fc,
            exercised=False,
            observed_fail_closed=None,
            observed_retry_behavior="NOT_EVALUATED",
            evidence_notes="Fault injection not performed.",
        )
        for fc in FailureClass
    }


def build_failure_matrix(
    *,
    contracts: dict[str, FailureContractItem] | None = None,
    observations: dict[str, FailureObservationItem] | None = None,
) -> FailureMatrix:
    cts = contracts if contracts is not None else get_default_failure_contracts()
    obs = observations if observations is not None else create_initial_failure_observations()

    all_contract_fc = all(c.expected_fail_closed for c in cts.values())

    # Honest evidence check: only true if all were actually exercised and proved fail-closed
    exercised_items = [o for o in obs.values() if o.exercised]
    if not exercised_items:
        all_obs_fc = None  # None indicates not evaluated
    else:
        all_obs_fc = len(exercised_items) == len(FailureClass) and all(
            o.observed_fail_closed is True for o in exercised_items
        )

    return FailureMatrix(
        schema=FAILURE_MATRIX_SCHEMA,
        contracts=cts,
        observations=obs,
        all_fail_closed_contract=all_contract_fc,
        all_fail_closed_observed=all_obs_fc,
    )
