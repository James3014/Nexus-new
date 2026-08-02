from __future__ import annotations

import pytest

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


@pytest.mark.parametrize(
    "field_name, invalid_value, expected_blocker",
    [
        ("identity_authority", "attacker.identity", "EP_AUTHORITY_IDENTITY_OVERRIDE"),
        ("task_authority", "attacker.task", "EP_AUTHORITY_TASK_OVERRIDE"),
        ("receipt_authority", "nexus.research.epistemic_profile", "EP_AUTHORITY_RECEIPT_OVERRIDE"),
        ("claim_boundary_authority", "attacker.claim_boundary", "EP_AUTHORITY_CLAIM_BOUNDARY_OVERRIDE"),
        ("claim_evidence_authority", "attacker.claim_evidence", "EP_AUTHORITY_CLAIM_EVIDENCE_OVERRIDE"),
        ("replay_authority", "attacker.replay", "EP_AUTHORITY_REPLAY_OVERRIDE"),
        ("acceptance_authority", "nexus.research.epistemic_profile", "EP_AUTHORITY_ACCEPTANCE_OVERRIDE"),
        ("integration_authority", "attacker.integrator", "EP_AUTHORITY_INTEGRATION_AUTHORITY_OVERRIDE"),
        ("profile_domain_authority", "attacker.profile_domain", "EP_AUTHORITY_PROFILE_DOMAIN_OVERRIDE"),
    ],
)
def test_all_authority_string_fields_must_match_canonical_value(field_name, invalid_value, expected_blocker):
    boundary = default_epistemic_authority_boundary().to_dict()
    boundary[field_name] = invalid_value
    blockers = validate_epistemic_authority_payload(boundary)
    assert expected_blocker in blockers


@pytest.mark.parametrize(
    "flag_name, expected_blocker",
    [
        ("profile_may_update_runtime", "EP_AUTHORITY_RUNTIME_UNLOCK"),
        ("profile_may_approve_candidate", "EP_AUTHORITY_CANDIDATE_APPROVAL_UNLOCK"),
        ("profile_may_integrate", "EP_AUTHORITY_INTEGRATION_UNLOCK"),
        ("profile_may_push", "EP_AUTHORITY_PUSH_UNLOCK"),
        ("profile_may_unlock_public_claim", "EP_AUTHORITY_PUBLIC_CLAIM_UNLOCK"),
        ("profile_may_unlock_public_benchmark", "EP_AUTHORITY_PUBLIC_BENCHMARK_UNLOCK"),
        ("profile_may_claim_production_ready", "EP_AUTHORITY_PRODUCTION_UNLOCK"),
    ],
)
def test_all_permission_flags_must_fail_closed_when_true(flag_name, expected_blocker):
    boundary = default_epistemic_authority_boundary().to_dict()
    boundary[flag_name] = True
    blockers = validate_epistemic_authority_payload(boundary)
    assert expected_blocker in blockers


def test_adversarial_full_override_payload_returns_all_blockers():
    payload = {
        "identity_authority": "attacker",
        "task_authority": "attacker",
        "receipt_authority": "attacker",
        "claim_boundary_authority": "attacker",
        "claim_evidence_authority": "attacker",
        "replay_authority": "attacker",
        "acceptance_authority": "attacker",
        "integration_authority": "attacker",
        "profile_domain_authority": "attacker",
        "profile_may_update_runtime": True,
        "profile_may_approve_candidate": True,
        "profile_may_integrate": True,
        "profile_may_push": True,
        "profile_may_unlock_public_claim": True,
        "profile_may_unlock_public_benchmark": True,
        "profile_may_claim_production_ready": True,
    }
    blockers = validate_epistemic_authority_payload(payload)
    assert len(blockers) == 16
    assert "EP_AUTHORITY_IDENTITY_OVERRIDE" in blockers
    assert "EP_AUTHORITY_TASK_OVERRIDE" in blockers
    assert "EP_AUTHORITY_RECEIPT_OVERRIDE" in blockers
    assert "EP_AUTHORITY_CLAIM_BOUNDARY_OVERRIDE" in blockers
    assert "EP_AUTHORITY_CLAIM_EVIDENCE_OVERRIDE" in blockers
    assert "EP_AUTHORITY_REPLAY_OVERRIDE" in blockers
    assert "EP_AUTHORITY_ACCEPTANCE_OVERRIDE" in blockers
    assert "EP_AUTHORITY_INTEGRATION_AUTHORITY_OVERRIDE" in blockers
    assert "EP_AUTHORITY_PROFILE_DOMAIN_OVERRIDE" in blockers
    assert "EP_AUTHORITY_RUNTIME_UNLOCK" in blockers
    assert "EP_AUTHORITY_CANDIDATE_APPROVAL_UNLOCK" in blockers
    assert "EP_AUTHORITY_INTEGRATION_UNLOCK" in blockers
    assert "EP_AUTHORITY_PUSH_UNLOCK" in blockers
    assert "EP_AUTHORITY_PUBLIC_CLAIM_UNLOCK" in blockers
    assert "EP_AUTHORITY_PUBLIC_BENCHMARK_UNLOCK" in blockers
    assert "EP_AUTHORITY_PRODUCTION_UNLOCK" in blockers


def test_benign_exact_payload_passes():
    boundary = default_epistemic_authority_boundary()
    blockers = validate_epistemic_authority_payload(boundary.to_dict())
    assert len(blockers) == 0
