"""Tests for claim boundary — fail-closed authority (RC-0)."""
from __future__ import annotations

from nexus.evidence.claim_boundary import (
    CLAIM_RULES,
    ClaimBoundary,
    evaluate_claim_boundary,
)


def test_defaults_fail_closed():
    b = ClaimBoundary()
    assert b.simulated is True
    assert b.claim_eligible is False
    assert b.receipt_present is False
    assert b.public_claim_allowed is False
    assert b.production_ready is False
    assert b.internal_only is True
    assert "defaults_fail_closed" in (b.claim_block_reason or "")


def test_bare_to_dict_fail_closed():
    d = ClaimBoundary().to_dict()
    assert d["public_claim_allowed"] is False
    assert d["production_ready"] is False
    assert d["monetary_claim_allowed"] is False
    assert d["training_export_allowed"] is False


def test_from_dict_empty_fail_closed():
    b = ClaimBoundary.from_dict({})
    assert b.public_claim_allowed is False
    assert b.simulated is True
    assert b.claim_eligible is False
    assert b.receipt_present is False


def test_from_dict_simulated_false_still_claim_false():
    b = ClaimBoundary.from_dict({"simulated": False})
    assert b.public_claim_allowed is False


def test_from_dict_producer_public_claim_true_ignored():
    b = ClaimBoundary.from_dict(
        {
            "simulated": False,
            "claim_eligible": True,
            "receipt_present": True,
            "model_calls": 5,
            "public_claim_allowed": True,
            "production_ready": True,
        }
    )
    assert b.public_claim_allowed is False
    assert b.production_ready is False
    assert "public_release_authority_required" in b.claim_block_reason


def test_simulated_blocks_public_claim():
    b = evaluate_claim_boundary(
        simulated=True,
        claim_eligible=True,
        receipt_present=True,
        model_calls=1,
    )
    assert b.public_claim_allowed is False
    assert "simulated=true" in b.claim_block_reason


def test_missing_receipt_blocks_public_claim():
    b = evaluate_claim_boundary(
        simulated=False,
        claim_eligible=True,
        receipt_present=False,
        model_calls=1,
    )
    assert b.public_claim_allowed is False
    assert "receipt_present=false" in b.claim_block_reason


def test_claim_not_eligible_blocks_public_claim():
    b = evaluate_claim_boundary(
        simulated=False,
        claim_eligible=False,
        receipt_present=True,
        model_calls=1,
    )
    assert b.public_claim_allowed is False
    assert "claim_eligible=false" in b.claim_block_reason


def test_zero_model_calls_blocks_public_claim():
    b = evaluate_claim_boundary(
        simulated=False,
        claim_eligible=True,
        receipt_present=True,
        model_calls=0,
    )
    assert b.public_claim_allowed is False
    assert "model_calls=0" in b.claim_block_reason


def test_multiple_blocks_combined():
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


def test_eligibility_green_still_no_public_claim():
    """Local eligibility may be complete; public claim stays locked."""
    b = evaluate_claim_boundary(
        simulated=False,
        claim_eligible=True,
        receipt_present=True,
        model_calls=5,
        visible_tests_passed=3,
        hidden_tests_passed=2,
    )
    assert b.public_claim_allowed is False
    assert b.eligibility_complete is True
    assert "public_release_authority_required" in b.claim_block_reason


def test_model_call_without_receipt_fail_closed():
    b = evaluate_claim_boundary(
        simulated=False,
        claim_eligible=True,
        receipt_present=False,
        model_calls=3,
    )
    assert b.public_claim_allowed is False
    assert b.evidence_complete is False


def test_claim_rules_are_defined():
    assert len(CLAIM_RULES) >= 4
    assert any("fail-closed" in r or "public_claim" in r for r in CLAIM_RULES)


def test_claim_boundary_roundtrip_stays_fail_closed():
    b = evaluate_claim_boundary(
        simulated=False,
        claim_eligible=True,
        receipt_present=True,
        model_calls=3,
    )
    d = b.to_dict()
    # producer tries to flip
    d["public_claim_allowed"] = True
    d["production_ready"] = True
    b2 = ClaimBoundary.from_dict(d)
    assert b2.public_claim_allowed is False
    assert b2.production_ready is False
    assert b2.model_calls == b.model_calls


def test_to_dict_has_legacy_and_additive_keys():
    d = ClaimBoundary().to_dict()
    for key in (
        "simulated",
        "claim_eligible",
        "receipt_present",
        "model_calls",
        "public_claim_allowed",
        "claim_block_reason",
        "value_measured",
        "monetary_claim_allowed",
        "routing_surface_changed",
        "production_ready",
        "internal_only",
        "solve_eligible",
        "training_export_allowed",
    ):
        assert key in d
