"""Tests for claim boundary."""
from __future__ import annotations

from nexus.evidence.claim_boundary import (
    ClaimBoundary,
    evaluate_claim_boundary,
    CLAIM_RULES,
)


def test_simulated_blocks_public_claim():
    """simulated=true -> public_claim_allowed=false."""
    b = evaluate_claim_boundary(
        simulated=True,
        claim_eligible=True,
        receipt_present=True,
        model_calls=1,
    )
    assert b.public_claim_allowed is False
    assert "simulated=true" in b.claim_block_reason


def test_missing_receipt_blocks_public_claim():
    """receipt_present=false -> public_claim_allowed=false."""
    b = evaluate_claim_boundary(
        simulated=False,
        claim_eligible=True,
        receipt_present=False,
        model_calls=1,
    )
    assert b.public_claim_allowed is False
    assert "receipt_present=false" in b.claim_block_reason


def test_claim_not_eligible_blocks_public_claim():
    """claim_eligible=false -> public_claim_allowed=false."""
    b = evaluate_claim_boundary(
        simulated=False,
        claim_eligible=False,
        receipt_present=True,
        model_calls=1,
    )
    assert b.public_claim_allowed is False
    assert "claim_eligible=false" in b.claim_block_reason


def test_zero_model_calls_blocks_public_claim():
    """model_calls=0 -> public_claim_allowed=false."""
    b = evaluate_claim_boundary(
        simulated=False,
        claim_eligible=True,
        receipt_present=True,
        model_calls=0,
    )
    assert b.public_claim_allowed is False
    assert "model_calls=0" in b.claim_block_reason


def test_multiple_blocks_combined():
    """Multiple blocking conditions combine."""
    b = evaluate_claim_boundary(
        simulated=True,
        claim_eligible=False,
        receipt_present=False,
        model_calls=0,
    )
    assert b.public_claim_allowed is False
    assert "simulated=true" in b.claim_block_reason
    assert "receipt_present=false" in b.claim_block_reason
    assert "claim_eligible=false" in b.claim_block_reason
    assert "model_calls=0" in b.claim_block_reason


def test_valid_boundary_allows_public_claim():
    """All conditions met -> public_claim_allowed=true."""
    b = evaluate_claim_boundary(
        simulated=False,
        claim_eligible=True,
        receipt_present=True,
        model_calls=5,
        visible_tests_passed=3,
        hidden_tests_passed=2,
    )
    assert b.public_claim_allowed is True
    assert b.claim_block_reason == ""


def test_claim_rules_are_defined():
    """CLAIM_RULES list exists and has entries."""
    assert len(CLAIM_RULES) >= 4


def test_claim_boundary_roundtrip():
    """to_dict and from_dict roundtrip."""
    b = evaluate_claim_boundary(
        simulated=False,
        claim_eligible=True,
        receipt_present=True,
        model_calls=3,
    )
    d = b.to_dict()
    b2 = ClaimBoundary.from_dict(d)
    assert b2.public_claim_allowed == b.public_claim_allowed
    assert b2.model_calls == b.model_calls
