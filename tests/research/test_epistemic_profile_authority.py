from __future__ import annotations

from nexus.research.epistemic_profile.authority import (
    EpistemicAuthorityBoundary,
    default_epistemic_authority_boundary,
    validate_epistemic_authority_payload,
)


def test_default_authority_points_to_nexus_authorities():
    boundary = default_epistemic_authority_boundary()
    assert boundary.identity_authority == "nexus.lifecycle"
    assert boundary.task_authority == "nexus.task_card"
    assert boundary.receipt_authority == "nexus.receipt"
    assert boundary.claim_boundary_authority == "nexus.evidence.claim_boundary"
    assert boundary.claim_evidence_authority == "nexus.contracts.claim_evidence_read_model"
    assert boundary.replay_authority == "nexus.replay"
    assert boundary.acceptance_authority == "nexus.acceptance"
    assert boundary.integration_authority == "owner_or_formal_integrator"
    assert boundary.profile_domain_authority == "nexus.research.epistemic_profile"


def test_profile_cannot_become_receipt_authority():
    payload = {"receipt_authority": "nexus.research.epistemic_profile"}
    blockers = validate_epistemic_authority_payload(payload)
    assert "EP_AUTHORITY_RECEIPT_OVERRIDE" in blockers


def test_profile_cannot_become_acceptance_authority():
    payload = {"acceptance_authority": "nexus.research.epistemic_profile"}
    blockers = validate_epistemic_authority_payload(payload)
    assert "EP_AUTHORITY_ACCEPTANCE_OVERRIDE" in blockers


def test_profile_cannot_update_runtime():
    payload = {"profile_may_update_runtime": True}
    blockers = validate_epistemic_authority_payload(payload)
    assert "EP_AUTHORITY_RUNTIME_UNLOCK" in blockers


def test_profile_cannot_unlock_public_claim():
    payload = {"profile_may_unlock_public_claim": True}
    blockers = validate_epistemic_authority_payload(payload)
    assert "EP_AUTHORITY_PUBLIC_CLAIM_UNLOCK" in blockers


def test_profile_cannot_unlock_public_benchmark():
    payload = {"profile_may_unlock_public_benchmark": True}
    blockers = validate_epistemic_authority_payload(payload)
    assert "EP_AUTHORITY_PUBLIC_BENCHMARK_UNLOCK" in blockers


def test_profile_cannot_approve_integration():
    payload = {"profile_may_integrate": True}
    blockers = validate_epistemic_authority_payload(payload)
    assert "EP_AUTHORITY_INTEGRATION_UNLOCK" in blockers


def test_profile_cannot_claim_production_readiness():
    payload = {"profile_may_claim_production_ready": True}
    blockers = validate_epistemic_authority_payload(payload)
    assert "EP_AUTHORITY_PRODUCTION_UNLOCK" in blockers


def test_multiple_simultaneous_overrides_return_all_stable_blockers():
    payload = {
        "receipt_authority": "override",
        "acceptance_authority": "override",
        "profile_may_update_runtime": True,
        "profile_may_unlock_public_claim": True,
        "profile_may_unlock_public_benchmark": True,
        "profile_may_integrate": True,
        "profile_may_claim_production_ready": True,
    }
    blockers = validate_epistemic_authority_payload(payload)
    assert len(blockers) == 7
    assert "EP_AUTHORITY_RECEIPT_OVERRIDE" in blockers
    assert "EP_AUTHORITY_ACCEPTANCE_OVERRIDE" in blockers
    assert "EP_AUTHORITY_RUNTIME_UNLOCK" in blockers
    assert "EP_AUTHORITY_PUBLIC_CLAIM_UNLOCK" in blockers
    assert "EP_AUTHORITY_PUBLIC_BENCHMARK_UNLOCK" in blockers
    assert "EP_AUTHORITY_INTEGRATION_UNLOCK" in blockers
    assert "EP_AUTHORITY_PRODUCTION_UNLOCK" in blockers


def test_benign_exact_payload_passes():
    boundary = default_epistemic_authority_boundary()
    blockers = validate_epistemic_authority_payload(boundary.to_dict())
    assert len(blockers) == 0
