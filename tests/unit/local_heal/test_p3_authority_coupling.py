from __future__ import annotations

import json
import pytest
from nexus.services.local_heal.p3_authority_coupling import (
    P3AuthorityCouplingDecision,
    compute_p3_authority_coupling,
    p3_authority_coupling_to_dict,
)


# ============================================================
# O4-1: no candidate cannot apply
# ============================================================


def test_no_candidate_cannot_apply():
    decision = compute_p3_authority_coupling(candidate_available=False)
    assert decision.patch_apply_allowed is False
    assert decision.solved_allowed is False


# ============================================================
# O4-2: synthetic candidate requires P2 apply/hash/anchor truth
# ============================================================


def test_synthetic_requires_p2():
    decision = compute_p3_authority_coupling(candidate_available=True, candidate_is_synthetic=True)
    assert decision.p2_apply_required is True
    assert decision.p2_hash_truth_required is True
    assert decision.p2_anchor_truth_required is True


# ============================================================
# O4-3: synthetic candidate requires P4 full verifier
# ============================================================


def test_synthetic_requires_p4_verifier():
    decision = compute_p3_authority_coupling(candidate_available=True, candidate_is_synthetic=True)
    assert decision.p4_full_verifier_required is True


# ============================================================
# O4-4: synthetic candidate requires P4 claim gate
# ============================================================


def test_synthetic_requires_p4_claim_gate():
    decision = compute_p3_authority_coupling(candidate_available=True, candidate_is_synthetic=True)
    assert decision.p4_claim_gate_required is True


# ============================================================
# O4-5: patch_apply_allowed=false always
# ============================================================


def test_patch_apply_allowed_always_false():
    decision = compute_p3_authority_coupling(candidate_available=True)
    assert decision.patch_apply_allowed is False


# ============================================================
# O4-6: solved_allowed=false always
# ============================================================


def test_solved_allowed_always_false():
    decision = compute_p3_authority_coupling(candidate_available=True)
    assert decision.solved_allowed is False


# ============================================================
# O4-7: claim_eligible_allowed=false always
# ============================================================


def test_claim_eligible_allowed_always_false():
    decision = compute_p3_authority_coupling(candidate_available=True)
    assert decision.claim_eligible_allowed is False


# ============================================================
# O4-8: public_claim_allowed=false always
# ============================================================


def test_public_claim_allowed_always_false():
    decision = compute_p3_authority_coupling(candidate_available=True)
    assert decision.public_claim_allowed is False


# ============================================================
# O4-9: production_ready=false always
# ============================================================


def test_production_ready_always_false():
    decision = compute_p3_authority_coupling(candidate_available=True)
    assert decision.production_ready is False


# ============================================================
# O4-10: missing P2 hash truth blocks
# ============================================================


def test_missing_p2_hash_truth_blocks():
    decision = compute_p3_authority_coupling(
        candidate_available=True, p2_hash_truth_present=False
    )
    assert "p2_hash_truth_missing" in decision.blocked_reasons


# ============================================================
# O4-11: missing P4 verifier blocks
# ============================================================


def test_missing_p4_verifier_blocks():
    decision = compute_p3_authority_coupling(
        candidate_available=True, p4_full_verifier_present=False
    )
    assert "p4_full_verifier_missing" in decision.blocked_reasons


# ============================================================
# O4-12: missing P4 claim gate blocks
# ============================================================


def test_missing_p4_claim_gate_blocks():
    decision = compute_p3_authority_coupling(
        candidate_available=True, p4_claim_gate_present=False
    )
    assert "p4_claim_gate_missing" in decision.blocked_reasons


# ============================================================
# O4-13: JSON serialization works
# ============================================================


def test_json_serializable():
    decision = compute_p3_authority_coupling(candidate_available=True)
    d = p3_authority_coupling_to_dict(decision)
    assert isinstance(json.dumps(d), str)
