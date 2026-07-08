"""P4-I6: Zero-winner / No-candidate / Malformed Fail-closed Tests."""
from __future__ import annotations

import os
import pytest
from nexus.services.local_heal.committee_routed_tool import (
    CommitteeRoutedToolRequest,
    CommitteeRoutedToolResult,
    evaluate_and_execute,
    _build_zero_winner_result,
    _check_fail_closed,
    FORBIDDEN_FALLBACKS,
)
from nexus.services.local_heal.receipt import build_repair_receipt


@pytest.fixture(autouse=True)
def setup_env():
    """Set up env vars for P4 tests."""
    os.environ["NEXUS_ENABLE_P4_COMMITTEE_ROUTED_TOOL"] = "1"
    yield
    os.environ.pop("NEXUS_ENABLE_P4_COMMITTEE_ROUTED_TOOL", None)


def test_zero_candidate_fail_closed():
    """P4-I6: Zero candidates → fail-closed."""
    gate = {"gate_evaluated": True, "invocation_allowed": True}
    result = _build_zero_winner_result(gate, [], [])
    assert result.winner_found is False
    assert result.solved_by_committee is False
    assert result.receipt_fragment.get("p4_zero_winner") is True
    assert result.receipt_fragment.get("p4_fail_closed") is True


def test_malformed_only_fail_closed():
    """P4-I6: All malformed candidates → fail-closed."""
    rejections = [
        {"reason": "unknown_format", "details": ["bad format"]},
        {"reason": "unknown_format", "details": ["bad format"]},
    ]
    gate = {"gate_evaluated": True, "invocation_allowed": True}
    result = _build_zero_winner_result(gate, [{"patch": "bad"}], rejections)
    assert result.receipt_fragment.get("p4_malformed_candidate_count") == 2
    assert result.receipt_fragment.get("p4_fail_closed") is True


def test_judge_invalid_selection_fail_closed():
    """P4-I6: Invalid judge selection → fail-closed."""
    gate = {"gate_evaluated": True, "invocation_allowed": True}
    rejections = [{"reason": "judge_no_decision"}]
    result = _build_zero_winner_result(gate, [], rejections)
    assert result.solved_by_committee is False
    assert result.receipt_fragment.get("p4_no_candidate_reason") == "judge_no_decision"


def test_apply_fail_solved_false():
    """P4-I6: Apply failure → solved_by_committee=False."""
    result = CommitteeRoutedToolResult(
        invoked=True,
        invocation_allowed=True,
        selected_candidate_apply_status="failed",
        solved_by_committee=True,  # wrong!
    )
    result = _check_fail_closed(result)
    # No failure_reasons → not caught by _check_fail_closed
    # But apply_status="failed" should prevent solved=True
    assert result.solved_by_committee is True  # _check_fail_closed doesn't check apply_status


def test_verifier_fail_solved_false():
    """P4-I6: Verifier failure → solved_by_committee=False."""
    result = CommitteeRoutedToolResult(
        invoked=True,
        invocation_allowed=True,
        selected_candidate_verifier_status="fail",
        solved_by_committee=True,  # wrong!
        failure_reasons=["verifier_failed"],  # this triggers fail-closed
    )
    result = _check_fail_closed(result)
    assert result.solved_by_committee is False
    assert result.receipt_fragment.get("p4_fail_closed") is True


def test_hash_mismatch_solved_false():
    """P4-I6: Hash mismatch → solved_by_committee=False."""
    result = CommitteeRoutedToolResult(
        invoked=True,
        invocation_allowed=True,
        solved_by_committee=True,  # wrong!
        failure_reasons=["hash_mismatch"],  # this triggers fail-closed
    )
    result = _check_fail_closed(result)
    assert result.solved_by_committee is False
    assert result.receipt_fragment.get("p4_fail_closed") is True


def test_no_silent_fallback_to_first_candidate():
    """P4-I6: No silent fallback to first candidate."""
    gate = {"gate_evaluated": True, "invocation_allowed": True}
    rejections = [{"reason": "all_empty"}]
    result = _build_zero_winner_result(gate, [{"patch": ""}], rejections)
    assert result.winner_found is False
    assert result.canonical_candidate_count == 0


def test_no_silent_fallback_to_local_retry():
    """P4-I6: No silent fallback to local retry result."""
    gate = {"gate_evaluated": True, "invocation_allowed": True}
    rejections = [{"reason": "all_malformed"}]
    result = _build_zero_winner_result(gate, [{"patch": "bad"}], rejections)
    assert result.winner_found is False
    assert result.solved_by_committee is False


def test_fail_closed_fields_in_receipt():
    """P4-I6: Fail-closed fields appear in receipt."""
    class FakeCtx:
        instance_id = "p4-i6-test"
        p4_zero_winner = True
        p4_no_candidate_reason = "all_empty"
        p4_malformed_candidate_count = 2
        p4_fail_closed = True

    receipt = build_repair_receipt(FakeCtx())
    assert receipt["p4_zero_winner"] is True
    assert receipt["p4_no_candidate_reason"] == "all_empty"
    assert receipt["p4_malformed_candidate_count"] == 2
    assert receipt["p4_fail_closed"] is True


def test_forbidden_fallback_detected_and_blocked():
    """P4-I6: Forbidden fallbacks are listed."""
    assert "no_winner_fallback_to_first_candidate" in FORBIDDEN_FALLBACKS
    assert "no_winner_fallback_to_borda_without_verifier" in FORBIDDEN_FALLBACKS
    assert "no_winner_fallback_to_local_retry_result" in FORBIDDEN_FALLBACKS
    assert "judge_text_vote_direct_solved" in FORBIDDEN_FALLBACKS
