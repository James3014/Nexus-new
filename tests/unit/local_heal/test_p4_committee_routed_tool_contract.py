"""P4-I1: Committee Routed-Tool Contract Tests."""
from __future__ import annotations

import os
import tempfile
import pytest
from nexus.services.local_heal.committee_routed_tool import (
    CommitteeCandidateProducer,
    CommitteeRoutedToolRequest,
    CommitteeRoutedToolResult,
    evaluate_and_execute,
    validate_committee_request,
    build_committee_receipt_fragment,
)
from nexus.services.local_heal.receipt import build_repair_receipt


# ── Helpers ──

_VALID_RAW_CANDIDATE = {
    "candidate_patch": "def foo():\n    return 42\n",
    "format": "UNIFIED_DIFF",
    "model": "test-proposer",
    "candidate_id": "cand-1",
}


def _valid_request(**overrides):
    """Build a CommitteeRoutedToolRequest that passes the activation gate."""
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


@pytest.fixture(autouse=True)
def setup_env():
    """Set up env vars for P4 tests."""
    os.environ["NEXUS_ENABLE_P4_COMMITTEE_ROUTED_TOOL"] = "1"
    yield
    os.environ.pop("NEXUS_ENABLE_P4_COMMITTEE_ROUTED_TOOL", None)


# ── Producer Seam Tests (P4-R1) ──


def test_producer_missing_fail_closed():
    """P4-R1: Gate allows but producer None → fail closed."""
    request = _valid_request()
    result = evaluate_and_execute(request, candidate_producer=None)
    assert result.invocation_allowed is True
    assert result.invoked is True
    assert "missing_committee_candidate_producer" in result.failure_reasons
    assert result.winner_found is False
    assert result.solved_by_committee is False
    assert result.receipt_fragment.get("p4_fail_closed") is True
    assert result.candidate_producer_present is False


def test_producer_raises_exception_fail_closed():
    """P4-R1: Producer raises → fail closed."""
    def broken_producer(request):
        raise RuntimeError("provider_down")

    request = _valid_request()
    result = evaluate_and_execute(request, candidate_producer=broken_producer)
    assert result.invoked is True
    assert result.candidate_producer_invoked is False
    assert "candidate_producer_error" in result.failure_reasons[0]
    assert result.solved_by_committee is False
    assert result.receipt_fragment.get("p4_fail_closed") is True


def test_producer_empty_candidates_fail_closed():
    """P4-R1: Producer returns empty list → zero-winner fail closed."""
    def empty_producer(request):
        return []

    request = _valid_request()
    result = evaluate_and_execute(request, candidate_producer=empty_producer)
    assert result.invoked is True
    assert result.candidate_producer_invoked is True
    assert result.winner_found is False
    assert result.solved_by_committee is False
    assert result.receipt_fragment.get("p4_zero_winner") is True
    assert result.receipt_fragment.get("p4_fail_closed") is True


def test_producer_missing_excluded_when_gate_blocks():
    """P4-R1: Gate blocks → producer not invoked."""
    request = _valid_request(proposer_specs=[], judge_model="")
    result = evaluate_and_execute(request, candidate_producer=None)
    assert result.invocation_allowed is False
    assert result.invoked is False
    assert result.solved_by_committee is False


def test_producer_fields_in_receipt():
    """P4-R1: Receipt fragment contains producer tracking fields."""
    def fake_producer(request):
        return [_VALID_RAW_CANDIDATE]

    with tempfile.TemporaryDirectory() as tmpdir:
        request = _valid_request(repo_root=tmpdir, source_hash="abc123")
        request.target_file = "foo.py"
        foo_path = os.path.join(tmpdir, "foo.py")
        with open(foo_path, "w") as f:
            f.write("x = 1\n")

        result = evaluate_and_execute(request, candidate_producer=fake_producer)
        assert result.candidate_producer_present is True
        assert result.candidate_producer_invoked is True
        assert result.raw_candidate_count == 1
        assert result.receipt_fragment.get("p4_candidate_producer_present") is True
        assert result.receipt_fragment.get("p4_candidate_producer_invoked") is True
        assert result.receipt_fragment.get("p4_raw_candidate_count") == 1


def test_request_contract_serializable():
    """P4-I1: Request can be created with defaults."""
    req = CommitteeRoutedToolRequest(
        task_id="t1",
        repo_root="/tmp",
        target_file="foo.py",
    )
    assert req.task_id == "t1"
    assert req.target_file == "foo.py"
    assert req.max_candidates == 3
    assert req.mutation_allowed is True


def test_result_contract_serializable():
    """P4-I1: Result can be created with defaults."""
    result = CommitteeRoutedToolResult()
    assert result.invoked is False
    assert result.failure_reasons == []
    assert result.receipt_fragment == {}


def test_validate_missing_target_file_fails():
    """P4-I1: Missing target_file fails validation."""
    req = CommitteeRoutedToolRequest(
        task_id="t1",
        repo_root="/tmp",
        target_file="",
        proposer_specs=[{"model": "a", "role": "primary"}, {"model": "b", "role": "secondary"}],
        judge_model="judge",
    )
    failures = validate_committee_request(req)
    assert "missing_target_file" in failures


def test_validate_insufficient_proposer_specs_fails():
    """P4-I1: Less than 2 proposer specs fails validation."""
    req = CommitteeRoutedToolRequest(
        task_id="t1",
        repo_root="/tmp",
        target_file="foo.py",
        proposer_specs=[{"model": "a", "role": "primary"}],
        judge_model="judge",
    )
    failures = validate_committee_request(req)
    assert "insufficient_proposer_specs" in failures


def test_validate_missing_judge_model_fails():
    """P4-I1: Missing judge_model fails validation."""
    req = CommitteeRoutedToolRequest(
        task_id="t1",
        repo_root="/tmp",
        target_file="foo.py",
        proposer_specs=[{"model": "a", "role": "primary"}, {"model": "b", "role": "secondary"}],
        judge_model="",
    )
    failures = validate_committee_request(req)
    assert "missing_judge_model" in failures


def test_validate_valid_request_passes():
    """P4-I1: Valid request passes validation."""
    req = CommitteeRoutedToolRequest(
        task_id="t1",
        repo_root="/tmp",
        target_file="foo.py",
        proposer_specs=[{"model": "a", "role": "primary"}, {"model": "b", "role": "secondary"}],
        judge_model="judge",
    )
    failures = validate_committee_request(req)
    assert failures == []


def test_build_receipt_fragment_contains_fields():
    """P4-I1: Receipt fragment contains all expected fields."""
    result = CommitteeRoutedToolResult(
        invoked=True,
        invocation_allowed=True,
        candidate_count=3,
        canonical_candidate_count=2,
        raw_candidate_count=5,
        candidate_producer_present=True,
        candidate_producer_invoked=True,
        candidate_producer_name="FakeProducer",
        selected_candidate_hash="abc123",
        selected_candidate_source_model="qwen",
        winner_found=True,
        solved_by_committee=True,
        receipt_fragment={
            "p4_selected_candidate_hash_matches_applied": True,
            "p4_committee_claim_gate_passed": True,
        },
    )
    fragment = build_committee_receipt_fragment(result)
    assert fragment["p4_committee_invoked"] is True
    assert fragment["p4_committee_candidate_count"] == 3
    assert fragment["p4_canonical_candidate_count"] == 2
    assert fragment["p4_raw_candidate_count"] == 5
    assert fragment["p4_candidate_producer_present"] is True
    assert fragment["p4_candidate_producer_invoked"] is True
    assert fragment["p4_candidate_producer_name"] == "FakeProducer"
    assert fragment["p4_selected_candidate_hash"] == "abc123"
    assert fragment["p4_winner_found"] is True
    assert fragment["p4_solved_by_committee"] is True
    assert fragment["p4_selected_candidate_hash_matches_applied"] is True
    assert fragment["p4_committee_claim_gate_passed"] is True
    assert fragment["p4_fail_closed"] is False


def test_receipt_fields_present_in_build_repair_receipt():
    """P4-I1: Receipt contains P4 fields."""
    class FakeCtx:
        instance_id = "p4-test"
        p4_committee_invoked = True
        p4_committee_invocation_allowed = True
        p4_committee_blocked_reason = ""
        p4_committee_candidate_count = 3
        p4_canonical_candidate_count = 2
        p4_selected_candidate_hash = "abc123"
        p4_selected_candidate_model = "qwen"
        p4_selected_candidate_apply_status = "applied"
        p4_selected_candidate_verifier_status = "pass"
        p4_winner_found = True
        p4_solved_by_committee = True
        p4_failure_reasons = []
        p4_fail_closed = False

    receipt = build_repair_receipt(FakeCtx())
    assert receipt["p4_committee_invoked"] is True
    assert receipt["p4_committee_candidate_count"] == 3
    assert receipt["p4_winner_found"] is True
    assert receipt["p4_solved_by_committee"] is True


def test_fail_closed_when_invalid_request():
    """P4-I1: Invalid request produces failure reasons."""
    req = CommitteeRoutedToolRequest(
        task_id="",
        repo_root="/tmp",
        target_file="",
        proposer_specs=[],
        judge_model="",
    )
    failures = validate_committee_request(req)
    assert len(failures) == 4
    assert "missing_target_file" in failures
    assert "insufficient_proposer_specs" in failures
    assert "missing_judge_model" in failures
    assert "missing_task_id" in failures


def test_result_defaults_are_fail_closed():
    """P4-I1: Default result has fail_closed=True when failure_reasons present."""
    result = CommitteeRoutedToolResult(failure_reasons=["blocked"])
    fragment = build_committee_receipt_fragment(result)
    assert fragment["p4_fail_closed"] is True
