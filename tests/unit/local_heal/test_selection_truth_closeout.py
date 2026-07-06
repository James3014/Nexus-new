"""C6Y: Selection truth closeout tests.

Ensures selection uses apply/verifier/hash truth signals, not just output_class.
"""
from __future__ import annotations

import pytest
from nexus.services.local_heal.candidate_envelope import CandidateEnvelope
from nexus.services.local_heal.candidate_decision_adapter import CandidateDecisionAdapter


def _make_candidate(cid, role, risk_flags=(), candidate_patch="patch",
                    output_class="", apply_success=False, verifier_result="",
                    hash_match=False, semantic_retry_outcome=""):
    return CandidateEnvelope(
        candidate_id=cid, task_id="task-1", source="local",
        model="test-model", role=role, patch_protocol="anchored_edit",
        target_file="app.py", target_symbol="run",
        source_anchor_hash="hash-1", candidate_patch_hash="hash-2",
        evidence_refs=("ref-1",), risk_flags=risk_flags,
        candidate_patch=candidate_patch,
        output_class=output_class,
        apply_success=apply_success,
        verifier_result=verifier_result,
        hash_match=hash_match,
        semantic_retry_outcome=semantic_retry_outcome,
    )


def test_selection_prefers_candidate_with_pass_or_stronger_retry_truth():
    """Selection should prefer candidate with verifier pass or stronger retry truth."""
    # Both have VALID_SEARCH_REPLACE, but secondary has verifier_result=pass
    c_primary = _make_candidate("c1", "primary_proposer",
                                output_class="VALID_SEARCH_REPLACE",
                                verifier_result="fail")
    c_secondary = _make_candidate("c2", "secondary_proposer",
                                  output_class="VALID_SEARCH_REPLACE",
                                  verifier_result="pass")

    resp = CandidateDecisionAdapter.select_candidate([c_secondary, c_primary])
    # Secondary should win because it has verifier_result=pass
    assert resp.selected_candidate_id == "c2"


def test_output_class_tie_uses_hash_apply_retry_truth():
    """When output_class ties, selection should use hash/apply/retry truth."""
    # Both VALID_SEARCH_REPLACE, but secondary has hash_match=True
    c_primary = _make_candidate("c1", "primary_proposer",
                                output_class="VALID_SEARCH_REPLACE",
                                hash_match=False)
    c_secondary = _make_candidate("c2", "secondary_proposer",
                                  output_class="VALID_SEARCH_REPLACE",
                                  hash_match=True)

    resp = CandidateDecisionAdapter.select_candidate([c_secondary, c_primary])
    # Secondary should win because it has hash_match=True
    assert resp.selected_candidate_id == "c2"


def test_role_priority_only_used_when_truth_signals_tie():
    """Role priority should only be used when all truth signals tie."""
    # Both have identical truth signals - verify they get same priority
    c_primary = _make_candidate("c1", "primary_proposer",
                                output_class="VALID_SEARCH_REPLACE",
                                verifier_result="fail",
                                hash_match=False,
                                apply_success=True)
    c_secondary = _make_candidate("c2", "secondary_proposer",
                                  output_class="VALID_SEARCH_REPLACE",
                                  verifier_result="fail",
                                  hash_match=False,
                                  apply_success=True)

    resp = CandidateDecisionAdapter.select_candidate([c_primary, c_secondary])
    # Primary should win by role_priority when all signals tie
    assert resp.selected_candidate_id == "c1"


def test_selection_remains_fail_closed():
    """Selection must remain fail-closed without verifier pass."""
    c_primary = _make_candidate("c1", "primary_proposer",
                                output_class="VALID_SEARCH_REPLACE",
                                verifier_result="fail",
                                risk_flags=("forbidden",))
    c_secondary = _make_candidate("c2", "secondary_proposer",
                                  output_class="VALID_SEARCH_REPLACE",
                                  verifier_result="fail")

    resp = CandidateDecisionAdapter.select_candidate([c_secondary, c_primary])
    # primary has forbidden flag, should be pruned
    assert resp.selected_candidate_id == "c2"
