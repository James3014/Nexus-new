from __future__ import annotations

import pytest

from nexus.engine.runtime_phase_contract import (
    LEGAL_RUNTIME_TRANSITIONS,
    PRODUCT_VISIBLE_PHASES,
    RUNTIME_PHASE_FLOW,
    RuntimePhase,
    RuntimeStatus,
    RuntimeTransitionError,
    legal_next,
    research_continuation,
    transition_values,
    validate_status,
    validate_transition,
)


def test_contract_has_one_runtime_phase_identity_and_product_visibility():
    assert tuple(phase.value for phase in RUNTIME_PHASE_FLOW) == ("S", "P", "D", "X", "R", "A", "C")
    assert tuple(phase.value for phase in PRODUCT_VISIBLE_PHASES) == ("P", "D", "X", "R", "A", "C")
    assert set(LEGAL_RUNTIME_TRANSITIONS) == set(RUNTIME_PHASE_FLOW)


@pytest.mark.parametrize(
    ("source", "target"),
    [
        ("S", "P"),
        ("P", "D"),
        ("D", "X"),
        ("D", "R"),
        ("X", "D"),
        ("R", "A"),
        ("A", "C"),
        ("A", "R"),
        ("A", "D"),
        ("C", "COMPLETE"),
    ],
)
def test_legal_transitions_are_normalized(source, target):
    audit_passed = True if (source, target) == ("A", "C") else None
    assert validate_transition(source, target, audit_passed=audit_passed) == (
        RuntimePhase(source),
        RuntimePhase(target) if target in {phase.value for phase in RuntimePhase} else RuntimeStatus(target),
    )


@pytest.mark.parametrize(
    ("source", "target"),
    [("S", "D"), ("P", "X"), ("X", "R"), ("R", "C"), ("C", "R"), ("A", "COMPLETE")],
)
def test_illegal_transitions_fail_closed(source, target):
    with pytest.raises(RuntimeTransitionError, match="illegal_runtime_transition"):
        validate_transition(source, target)


def test_audit_to_crystallize_requires_explicit_pass():
    with pytest.raises(RuntimeTransitionError, match="audit_pass_required"):
        validate_transition(RuntimePhase.A, RuntimePhase.C)
    assert validate_transition(RuntimePhase.A, RuntimePhase.C, audit_passed=True) == (RuntimePhase.A, RuntimePhase.C)


def test_diagnose_research_returns_to_same_diagnose_phase():
    assert research_continuation(external_research_required=True) == (RuntimePhase.X, RuntimePhase.D)
    assert research_continuation(external_research_required=False) == (RuntimePhase.D, RuntimePhase.R)


def test_status_vocabulary_and_serialization_are_strict():
    assert validate_status("recoverable_block") is RuntimeStatus.RECOVERABLE_BLOCK
    assert transition_values(RuntimePhase.A) == ("C", "D", "HARD_BLOCK", "R", "RECOVERABLE_BLOCK")
    with pytest.raises(RuntimeTransitionError, match="unknown_runtime_status"):
        validate_status("AUTO_APPROVE")
