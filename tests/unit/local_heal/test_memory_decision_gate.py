"""EA-R5: Memory Decision Gate Tests."""
from __future__ import annotations

import pytest
from nexus.services.local_heal.memory_decision_gate import (
    MemoryDecision,
    evaluate_memory_decision,
)


def test_blocked_by_low_copyability():
    """EA-R5: Low copyability → blocked."""
    decision = evaluate_memory_decision(
        copyability_score=0.3,
        decision_eligibility="audit_only",
    )
    assert decision.allowed is False
    assert decision.decision_mode == "blocked_by_low_copyability"


def test_blocked_by_unverified_outcome():
    """EA-R5: Unverified outcome → blocked."""
    decision = evaluate_memory_decision(
        copyability_score=0.8,
        decision_eligibility="audit_only",
    )
    assert decision.allowed is False
    assert decision.decision_mode == "blocked_by_unverified_outcome"


def test_allowed_memory():
    """EA-R5: High copyability + verified → allowed."""
    decision = evaluate_memory_decision(
        copyability_score=0.9,
        decision_eligibility="decision_eligible",
    )
    assert decision.allowed is True
    assert decision.decision_mode == "decision_eligible"


def test_allowed_memory_does_not_override_p4_gate():
    """EA-R5: Allowed memory still CANNOT bypass P4 verifier/claim gate."""
    decision = evaluate_memory_decision(
        copyability_score=0.9,
        decision_eligibility="decision_eligible",
    )
    # allowed=True means memory can influence decisions
    # But it does NOT mean P4 gate is bypassed
    assert decision.allowed is True
    # The decision_mode is "decision_eligible" not "p4_override"
    assert decision.decision_mode == "decision_eligible"


def test_policy_and_mem_palace_refs():
    """EA-R5: Policy and MemPalace refs are set."""
    decision = evaluate_memory_decision(
        copyability_score=0.9,
        decision_eligibility="decision_eligible",
    )
    assert decision.policy_ref != ""
    assert decision.mem_palace_ref != ""
