"""P4-I1: Committee Routed-Tool Contract Tests."""
from __future__ import annotations

import pytest
from nexus.services.local_heal.committee_routed_tool import (
    CommitteeRoutedToolRequest,
    CommitteeRoutedToolResult,
    validate_committee_request,
    build_committee_receipt_fragment,
)
from nexus.services.local_heal.receipt import build_repair_receipt


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
        selected_candidate_hash="abc123",
        selected_candidate_source_model="qwen",
        winner_found=True,
        solved_by_committee=True,
    )
    fragment = build_committee_receipt_fragment(result)
    assert fragment["p4_committee_invoked"] is True
    assert fragment["p4_committee_candidate_count"] == 3
    assert fragment["p4_canonical_candidate_count"] == 2
    assert fragment["p4_selected_candidate_hash"] == "abc123"
    assert fragment["p4_winner_found"] is True
    assert fragment["p4_solved_by_committee"] is True
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
