"""Lifecycle State Machine and Stop Condition Evaluator for Provider Adoption Experiments.

Schema: nexus.provider_experiment.lifecycle_state.v1
Governs the sequential execution through gates G0 to G6:
DRAFT → CONTRACT_FROZEN → IDENTITY_INSPECTED → CAPABILITY_PROBED →
COHORT_EVALUATED → OPERATIONAL_EVALUATED → FAILURE_EVALUATED → RECOMMENDATION_READY

Terminal States:
- BLOCKED_BY_ENVIRONMENT
- STOPPED_BY_CONDITION
- FAILED

False-Green Defense (Invariant 6.4):
- stop_conditions defined in the experiment contract are actively evaluated during cohort execution.
- If consecutive failures, error rate, total failures, or safety timeout threshold is crossed,
  the state machine transitions to STOPPED_BY_CONDITION and aborts all subsequent case executions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from nexus.calibration.provider_adoption.contracts import StopConditions

LIFECYCLE_SCHEMA = "nexus.provider_experiment.lifecycle_state.v1"


class LifecycleState(str, Enum):
    DRAFT = "DRAFT"
    CONTRACT_FROZEN = "CONTRACT_FROZEN"
    IDENTITY_INSPECTED = "IDENTITY_INSPECTED"
    CAPABILITY_PROBED = "CAPABILITY_PROBED"
    COHORT_EVALUATED = "COHORT_EVALUATED"
    OPERATIONAL_EVALUATED = "OPERATIONAL_EVALUATED"
    FAILURE_EVALUATED = "FAILURE_EVALUATED"
    RECOMMENDATION_READY = "RECOMMENDATION_READY"
    BLOCKED_BY_ENVIRONMENT = "BLOCKED_BY_ENVIRONMENT"
    STOPPED_BY_CONDITION = "STOPPED_BY_CONDITION"
    FAILED = "FAILED"


VALID_TRANSITIONS: dict[LifecycleState, set[LifecycleState]] = {
    LifecycleState.DRAFT: {
        LifecycleState.CONTRACT_FROZEN,
        LifecycleState.FAILED,
    },
    LifecycleState.CONTRACT_FROZEN: {
        LifecycleState.IDENTITY_INSPECTED,
        LifecycleState.BLOCKED_BY_ENVIRONMENT,
        LifecycleState.FAILED,
    },
    LifecycleState.IDENTITY_INSPECTED: {
        LifecycleState.CAPABILITY_PROBED,
        LifecycleState.BLOCKED_BY_ENVIRONMENT,
        LifecycleState.FAILED,
    },
    LifecycleState.CAPABILITY_PROBED: {
        LifecycleState.COHORT_EVALUATED,
        LifecycleState.STOPPED_BY_CONDITION,
        LifecycleState.FAILED,
    },
    LifecycleState.COHORT_EVALUATED: {
        LifecycleState.OPERATIONAL_EVALUATED,
        LifecycleState.STOPPED_BY_CONDITION,
        LifecycleState.FAILED,
    },
    LifecycleState.OPERATIONAL_EVALUATED: {
        LifecycleState.FAILURE_EVALUATED,
        LifecycleState.FAILED,
    },
    LifecycleState.FAILURE_EVALUATED: {
        LifecycleState.RECOMMENDATION_READY,
        LifecycleState.FAILED,
    },
    LifecycleState.RECOMMENDATION_READY: set(),
    LifecycleState.BLOCKED_BY_ENVIRONMENT: set(),
    LifecycleState.STOPPED_BY_CONDITION: set(),
    LifecycleState.FAILED: set(),
}


@dataclass
class LifecycleStateMachine:
    experiment_id: str
    current_state: LifecycleState = LifecycleState.DRAFT
    history: list[tuple[LifecycleState, str]] = field(default_factory=list)
    stop_reason: str = ""

    def __post_init__(self) -> None:
        if not self.history:
            self.history.append((self.current_state, "Initialized at DRAFT."))

    def transition_to(self, next_state: LifecycleState, reason: str = "") -> None:
        allowed = VALID_TRANSITIONS.get(self.current_state, set())
        if next_state not in allowed:
            raise ValueError(
                f"INVALID_LIFECYCLE_TRANSITION: Cannot transition from {self.current_state.value} to {next_state.value}."
            )
        self.current_state = next_state
        self.history.append((next_state, reason))
        if next_state in (
            LifecycleState.STOPPED_BY_CONDITION,
            LifecycleState.BLOCKED_BY_ENVIRONMENT,
            LifecycleState.FAILED,
        ):
            self.stop_reason = reason

    def check_stop_conditions(
        self,
        stop_conditions: StopConditions,
        *,
        consecutive_failures: int,
        total_failures: int,
        total_executed: int,
        timed_out: bool = False,
    ) -> tuple[bool, str]:
        """Evaluate whether execution must halt immediately (Invariant 6.4)."""
        if timed_out and stop_conditions.safety_abort_on_timeout:
            return True, "Safety abort triggered by operation timeout."

        if consecutive_failures >= stop_conditions.max_consecutive_failures:
            return True, (
                f"Stop condition triggered: consecutive failures ({consecutive_failures}) "
                f"reached limit ({stop_conditions.max_consecutive_failures})."
            )

        if total_failures >= stop_conditions.max_total_failures:
            return True, (
                f"Stop condition triggered: total failures ({total_failures}) "
                f"reached limit ({stop_conditions.max_total_failures})."
            )

        if total_executed >= 3:
            current_error_rate = total_failures / total_executed
            if current_error_rate > stop_conditions.max_error_rate:
                return True, (
                    f"Stop condition triggered: error rate ({current_error_rate:.2f}) "
                    f"exceeded threshold ({stop_conditions.max_error_rate:.2f})."
                )

        return False, ""
