"""Canonical runtime phase and transition contract.

This module is deliberately limited to runtime lifecycle semantics. Routing,
development-task state, approval, integration and learning authority remain
owned by their existing subsystems.
"""

from __future__ import annotations

from enum import Enum
from typing import Iterable


class RuntimePhase(str, Enum):
    """Runtime execution phases, including the non-visible specification gate."""

    S = "S"
    P = "P"
    D = "D"
    X = "X"
    R = "R"
    A = "A"
    C = "C"


class RuntimeStatus(str, Enum):
    """Shared decision and terminal vocabulary for runtime transitions."""

    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    REJECTED = "REJECTED"
    VETO = "VETO"
    REPLAN = "REPLAN"
    ESCALATED = "ESCALATED"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    RECOVERABLE_BLOCK = "RECOVERABLE_BLOCK"
    HARD_BLOCK = "HARD_BLOCK"
    CANCELLED = "CANCELLED"
    COLLISION_REJECT = "COLLISION_REJECT"
    COMPLETE = "COMPLETE"


RUNTIME_PHASE_FLOW: tuple[RuntimePhase, ...] = tuple(RuntimePhase)
PRODUCT_VISIBLE_PHASES: tuple[RuntimePhase, ...] = (
    RuntimePhase.P,
    RuntimePhase.D,
    RuntimePhase.X,
    RuntimePhase.R,
    RuntimePhase.A,
    RuntimePhase.C,
)

# A transition target is either another runtime phase or an explicit decision
# / terminal status. Statuses are included only where the contract permits them.
LEGAL_RUNTIME_TRANSITIONS: dict[RuntimePhase, frozenset[RuntimePhase | RuntimeStatus]] = {
    RuntimePhase.S: frozenset({RuntimePhase.P, RuntimeStatus.HARD_BLOCK}),
    RuntimePhase.P: frozenset({RuntimePhase.D, RuntimeStatus.HARD_BLOCK}),
    RuntimePhase.D: frozenset({
        RuntimePhase.X,
        RuntimePhase.R,
        RuntimePhase.P,
        RuntimeStatus.RECOVERABLE_BLOCK,
        RuntimeStatus.HARD_BLOCK,
    }),
    RuntimePhase.X: frozenset({
        RuntimePhase.D,
        RuntimeStatus.RECOVERABLE_BLOCK,
        RuntimeStatus.HARD_BLOCK,
    }),
    RuntimePhase.R: frozenset({
        RuntimePhase.A,
        RuntimePhase.D,
        RuntimeStatus.RECOVERABLE_BLOCK,
        RuntimeStatus.HARD_BLOCK,
    }),
    RuntimePhase.A: frozenset({
        RuntimePhase.C,
        RuntimePhase.R,
        RuntimePhase.D,
        RuntimeStatus.RECOVERABLE_BLOCK,
        RuntimeStatus.HARD_BLOCK,
    }),
    RuntimePhase.C: frozenset({
        RuntimeStatus.COMPLETE,
        RuntimeStatus.FAILED,
        RuntimeStatus.HUMAN_REVIEW,
    }),
}


class RuntimeTransitionError(ValueError):
    """Raised when a runtime phase transition is not contractually legal."""


def _phase(value: RuntimePhase | str) -> RuntimePhase:
    if isinstance(value, RuntimePhase):
        return value
    try:
        return RuntimePhase(str(value).strip().upper())
    except ValueError as exc:
        raise RuntimeTransitionError(f"unknown_runtime_phase:{value}") from exc


def _target(value: RuntimePhase | RuntimeStatus | str) -> RuntimePhase | RuntimeStatus:
    if isinstance(value, (RuntimePhase, RuntimeStatus)):
        return value
    raw = str(value).strip().upper()
    try:
        return RuntimePhase(raw)
    except ValueError:
        try:
            return RuntimeStatus(raw)
        except ValueError as exc:
            raise RuntimeTransitionError(f"unknown_runtime_transition_target:{value}") from exc


def legal_next(phase: RuntimePhase | str) -> frozenset[RuntimePhase | RuntimeStatus]:
    """Return the immutable set of legal next phases/statuses."""

    return LEGAL_RUNTIME_TRANSITIONS[_phase(phase)]


def validate_transition(
    phase: RuntimePhase | str,
    target: RuntimePhase | RuntimeStatus | str,
    *,
    audit_passed: bool | None = None,
) -> tuple[RuntimePhase, RuntimePhase | RuntimeStatus]:
    """Validate and return a normalized runtime transition.

    `A → C` requires an explicit audit pass. A missing audit result is not
    treated as success, preserving the fail-closed completion boundary.
    """

    source = _phase(phase)
    destination = _target(target)
    if destination not in legal_next(source):
        raise RuntimeTransitionError(f"illegal_runtime_transition:{source.value}->{destination.value}")
    if source is RuntimePhase.A and destination is RuntimePhase.C and audit_passed is not True:
        raise RuntimeTransitionError("audit_pass_required_for_crystallize")
    return source, destination


def validate_status(value: RuntimeStatus | str) -> RuntimeStatus:
    """Normalize one status and reject labels outside the shared vocabulary."""

    if isinstance(value, RuntimeStatus):
        return value
    try:
        return RuntimeStatus(str(value).strip().upper())
    except ValueError as exc:
        raise RuntimeTransitionError(f"unknown_runtime_status:{value}") from exc


def research_continuation(*, external_research_required: bool) -> tuple[RuntimePhase, RuntimePhase]:
    """Return the Diagnose branch, with research returning to the same D phase."""

    if external_research_required:
        validate_transition(RuntimePhase.D, RuntimePhase.X)
        validate_transition(RuntimePhase.X, RuntimePhase.D)
        return RuntimePhase.X, RuntimePhase.D
    validate_transition(RuntimePhase.D, RuntimePhase.R)
    return RuntimePhase.D, RuntimePhase.R


def transition_values(phase: RuntimePhase | str) -> tuple[str, ...]:
    """Serialize legal targets deterministically for receipts and tooling."""

    return tuple(sorted(target.value for target in legal_next(phase)))


def statuses(values: Iterable[RuntimeStatus | str]) -> tuple[RuntimeStatus, ...]:
    """Normalize a sequence of statuses without silently inventing labels."""

    return tuple(validate_status(value) for value in values)
