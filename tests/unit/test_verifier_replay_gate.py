"""Tests for verifier_replay_gate module."""

import pytest
from nexus.services.local_heal.verifier_replay_gate import (
    evaluate_verifier_replay_eligibility,
    VerifierReplayDecisionKind,
    VerifierReplayDecision,
)


def test_eligible_case():
    result = evaluate_verifier_replay_eligibility({
        "task_id": "test", "model": "14B",
        "source_available": True,
        "ast_locator_result": {"status": "ok", "span_start": 1, "span_end": 5},
        "source_hash_guard_result": {"hash_verified": True},
        "preview_result": {"preview_ok": True, "ast_valid": True},
    })
    assert result.eligible is True
    assert result.decision_kind == VerifierReplayDecisionKind.ELIGIBLE_FOR_VERIFIER_REPLAY


def test_source_unavailable():
    result = evaluate_verifier_replay_eligibility({
        "task_id": "test", "model": "14B", "source_available": False,
    })
    assert result.eligible is False
    assert result.decision_kind == VerifierReplayDecisionKind.NOT_ELIGIBLE_SOURCE_UNAVAILABLE


def test_symbol_not_found():
    result = evaluate_verifier_replay_eligibility({
        "task_id": "test", "model": "14B", "source_available": True,
        "ast_locator_result": {"status": "error", "error_kind": "SYMBOL_NOT_FOUND"},
    })
    assert result.eligible is False
    assert result.decision_kind == VerifierReplayDecisionKind.NOT_ELIGIBLE_SYMBOL_NOT_FOUND


def test_ambiguous_symbol():
    result = evaluate_verifier_replay_eligibility({
        "task_id": "test", "model": "14B", "source_available": True,
        "ast_locator_result": {"status": "error", "error_kind": "AMBIGUOUS_SYMBOL"},
    })
    assert result.eligible is False
    assert result.decision_kind == VerifierReplayDecisionKind.NOT_ELIGIBLE_AMBIGUOUS_SYMBOL


def test_source_stale():
    result = evaluate_verifier_replay_eligibility({
        "task_id": "test", "model": "14B", "source_available": True,
        "ast_locator_result": {"status": "ok", "span_start": 1, "span_end": 5},
        "source_hash_guard_result": {"hash_verified": False},
    })
    assert result.eligible is False
    assert result.decision_kind == VerifierReplayDecisionKind.NOT_ELIGIBLE_SOURCE_STALE


def test_ast_invalid():
    result = evaluate_verifier_replay_eligibility({
        "task_id": "test", "model": "14B", "source_available": True,
        "ast_locator_result": {"status": "ok", "span_start": 1, "span_end": 5},
        "source_hash_guard_result": {"hash_verified": True},
        "preview_result": {"preview_ok": False, "ast_valid": False},
    })
    assert result.eligible is False
    assert result.decision_kind == VerifierReplayDecisionKind.NOT_ELIGIBLE_AST_INVALID


def test_governance_enforced():
    result = evaluate_verifier_replay_eligibility({
        "task_id": "test", "model": "14B", "source_available": True,
        "ast_locator_result": {"status": "ok", "span_start": 1, "span_end": 5},
        "source_hash_guard_result": {"hash_verified": True},
        "preview_result": {"preview_ok": True, "ast_valid": True},
    })
    assert result.governance["verifier_run"] is False
    assert result.governance["m6_executed"] is False
    assert result.governance["training_export"] is False
    assert result.governance["public_claim_allowed"] is False
