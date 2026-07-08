"""P4-I5: Winner Re-apply + Verifier + Claim Gate Tests."""
from __future__ import annotations

import os
import pytest
import tempfile
from nexus.services.local_heal.committee_routed_tool import (
    CommitteeRoutedToolRequest,
    CommitteeRoutedToolResult,
    evaluate_and_execute,
    _apply_candidate,
    _verify_applied_candidate,
    _build_zero_winner_result,
)
from nexus.services.local_heal.output_understanding import CanonicalPatchCandidate
from nexus.services.local_heal.receipt import build_repair_receipt


@pytest.fixture(autouse=True)
def setup_env():
    """Set up env vars for P4 tests."""
    os.environ["NEXUS_ENABLE_P4_COMMITTEE_ROUTED_TOOL"] = "1"
    yield
    os.environ.pop("NEXUS_ENABLE_P4_COMMITTEE_ROUTED_TOOL", None)


def _valid_request(**overrides):
    defaults = {
        "task_id": "t1",
        "repo_root": "/tmp",
        "target_file": "foo.py",
        "difficulty": "hard",
        "execution_topology": "cloud_with_local_assist",
        "p3_route_status": "shadow_stage5_escalation_recommended",
        "hard_case_escalation_reason": "retry_failed",
        "proposer_specs": [{"model": "a", "role": "primary"}, {"model": "b", "role": "secondary"}],
        "judge_model": "judge",
    }
    defaults.update(overrides)
    return CommitteeRoutedToolRequest(**defaults)


def _make_candidate(patch="return 42"):
    return CanonicalPatchCandidate(
        source_format="SEARCH_REPLACE",
        raw_output=patch,
        raw_output_hash=hashlib.sha256(patch.encode("utf-8")).hexdigest(),
        normalized_patch=patch,
        normalized_patch_hash="",
        normalization_steps=(),
        safety_flags=(),
        target_file="foo.py",
    )


import hashlib


def test_winner_apply_success_claim_passes():
    """P4-I5: Winner apply + verifier + claim gate all pass."""
    with tempfile.TemporaryDirectory() as tmpdir:
        request = _valid_request(repo_root=tmpdir)
        candidate = _make_candidate("x = 42\n")

        apply_result = _apply_candidate(candidate, request)
        assert apply_result["applied"] is True

        verifier_result = _verify_applied_candidate(candidate, request)
        assert verifier_result["status"] == "pass"


def test_winner_apply_fails_solved_false():
    """P4-I5: Apply failure → solved_by_committee=False."""
    request = _valid_request(mutation_allowed=False)
    candidate = _make_candidate()
    apply_result = _apply_candidate(candidate, request)
    assert apply_result["applied"] is False


def test_winner_verifier_fails_solved_false():
    """P4-I5: Verifier failure → solved_by_committee=False."""
    with tempfile.TemporaryDirectory() as tmpdir:
        request = _valid_request(repo_root=tmpdir, target_file="bad.py")
        candidate = CanonicalPatchCandidate(
            source_format="SEARCH_REPLACE",
            raw_output="def bad(:",
            raw_output_hash="abc",
            normalized_patch="def bad(:",
            normalized_patch_hash="",
            normalization_steps=(),
            safety_flags=(),
            target_file="bad.py",
        )
        verifier_result = _verify_applied_candidate(candidate, request)
        assert verifier_result["status"] == "fail"


def test_winner_hash_mismatch_solved_false():
    """P4-I5: Hash mismatch → solved_by_committee=False."""
    with tempfile.TemporaryDirectory() as tmpdir:
        request = _valid_request(repo_root=tmpdir)
        candidate = CanonicalPatchCandidate(
            source_format="SEARCH_REPLACE",
            raw_output="original",
            raw_output_hash="wrong_hash",
            normalized_patch="applied",
            normalized_patch_hash="",
            normalization_steps=(),
            safety_flags=(),
            target_file="foo.py",
        )
        apply_result = _apply_candidate(candidate, request)
        assert apply_result["applied"] is True
        assert apply_result["hash_matches"] is False


def test_no_winner_fail_closed():
    """P4-I5: No valid candidates → fail-closed result."""
    gate = {"gate_evaluated": True, "invocation_allowed": True}
    result = _build_zero_winner_result(gate, [], [])
    assert result.winner_found is False
    assert result.solved_by_committee is False
    assert result.canonical_candidate_count == 0


def test_claim_gate_not_relaxed():
    """P4-I5: P2 claim gate is NOT relaxed for committee."""
    from nexus.services.local_heal.claim_delivery_gate import ClaimDeliveryGate
    gate = ClaimDeliveryGate()

    # Without source_hash → should fail
    decision = gate.validate({
        "verifier_status": "pass",
        "source_hash": "",
        "patch_applied": True,
        "candidate_hash_matches_applied": True,
        "candidate_target_file": "foo.py",
        "artifact_refs": [],
    })
    assert decision.claim_gate_passed is False
    assert "missing_source_hash" in decision.reasons


def test_solved_by_committee_true_all_conditions():
    """P4-I5: solved_by_committee=True requires all conditions."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create target file first
        target_path = os.path.join(tmpdir, "foo.py")
        with open(target_path, "w") as f:
            f.write("x = 1\n")

        request = _valid_request(repo_root=tmpdir, source_hash="abc123")
        candidate = _make_candidate("x = 42\n")

        apply_result = _apply_candidate(candidate, request)
        verifier_result = _verify_applied_candidate(candidate, request)

        from nexus.services.local_heal.claim_delivery_gate import ClaimDeliveryGate
        claim_gate = ClaimDeliveryGate()
        claim_decision = claim_gate.validate({
            "verifier_status": "pass",
            "verifier_artifact": "verification_report.txt",
            "source_hash": "abc123",
            "patch_applied": True,
            "candidate_hash_matches_applied": True,
            "candidate_target_file": "foo.py",
            "artifact_refs": ["patch.diff"],
        })

        solved = (
            apply_result["applied"]
            and verifier_result["status"] == "pass"
            and apply_result["hash_matches"]
            and claim_decision.claim_gate_passed
        )
        assert solved is True


def test_apply_verifier_claim_fields_in_receipt():
    """P4-I5: Receipt contains apply/verifier/claim fields."""
    class FakeCtx:
        instance_id = "p4-i5-test"
        p4_selected_candidate_apply_status = "applied"
        p4_selected_candidate_verifier_status = "pass"
        p4_committee_claim_gate_passed = True
        p4_solved_by_committee = True

    receipt = build_repair_receipt(FakeCtx())
    assert receipt["p4_selected_candidate_apply_status"] == "applied"
    assert receipt["p4_selected_candidate_verifier_status"] == "pass"
    assert receipt["p4_committee_claim_gate_passed"] is True
    assert receipt["p4_solved_by_committee"] is True
