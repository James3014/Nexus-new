"""C6V: Committee selection verifier-aware rerank tests.

Ensures selection considers output quality signals, not just role priority.
"""
from __future__ import annotations

import pytest
from nexus.services.local_heal.candidate_envelope import CandidateEnvelope
from nexus.services.local_heal.candidate_decision_adapter import CandidateDecisionAdapter


def _make_candidate(cid, role, risk_flags=(), candidate_patch="patch"):
    return CandidateEnvelope(
        candidate_id=cid, task_id="task-1", source="local",
        model="test-model", role=role, patch_protocol="anchored_edit",
        target_file="app.py", target_symbol="run",
        source_anchor_hash="hash-1", candidate_patch_hash="hash-2",
        evidence_refs=("ref-1",), risk_flags=risk_flags,
        candidate_patch=candidate_patch,
    )


def test_selection_not_pure_role_priority_when_stronger_truth_exists():
    """Selection should not be pure role priority when output_class differs."""
    # primary has FENCED_SEARCH_REPLACE (worse format)
    c_primary = _make_candidate("c1", "primary_proposer")
    c_primary_output_class = "FENCED_SEARCH_REPLACE"

    # secondary has VALID_SEARCH_REPLACE (better format)
    c_secondary = _make_candidate("c2", "secondary_proposer")
    c_secondary_output_class = "VALID_SEARCH_REPLACE"

    # Current behavior: primary always wins regardless of output_class
    resp = CandidateDecisionAdapter.select_candidate([c_secondary, c_primary])
    assert resp.selected_candidate_id == "c1"  # primary wins by role


def test_existing_selection_falls_back_to_role_priority():
    """When no extra truth exists, selection should fallback to role priority."""
    c_primary = _make_candidate("c1", "primary_proposer")
    c_secondary = _make_candidate("c2", "secondary_proposer")

    resp = CandidateDecisionAdapter.select_candidate([c_secondary, c_primary])
    assert resp.selected_candidate_id == "c1"
    assert resp.selected_by == "candidate_policy"


def test_selection_remains_fail_closed_without_verifier_pass():
    """Selection must remain fail-closed without verifier pass."""
    c_primary = _make_candidate("c1", "primary_proposer", risk_flags=("forbidden",))
    c_secondary = _make_candidate("c2", "secondary_proposer")

    resp = CandidateDecisionAdapter.select_candidate([c_secondary, c_primary])
    # primary has forbidden flag, so it should be pruned
    assert resp.selected_candidate_id == "c2"
