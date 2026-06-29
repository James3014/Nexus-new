from __future__ import annotations

import pytest
from nexus.services.local_heal.candidate_envelope import CandidateEnvelope
from nexus.services.local_heal.candidate_decision_adapter import CandidateDecisionAdapter


def test_select_candidate_primary_preferred() -> None:
    c1 = CandidateEnvelope(
        candidate_id="cand-primary",
        task_id="task-1",
        source="local",
        model="qwen-7b",
        role="primary_proposer",
        patch_protocol="anchored_edit",
        target_file="app.py",
        target_symbol="run",
        source_anchor_hash="hash-1",
        candidate_patch_hash="hash-2",
        evidence_refs=("ref-1",),
        candidate_patch="print('primary')",
    )
    c2 = CandidateEnvelope(
        candidate_id="cand-secondary",
        task_id="task-1",
        source="local",
        model="ds-6.7b",
        role="secondary_proposer",
        patch_protocol="anchored_edit",
        target_file="app.py",
        target_symbol="run",
        source_anchor_hash="hash-1",
        candidate_patch_hash="hash-3",
        evidence_refs=("ref-1",),
        candidate_patch="print('secondary')",
    )

    resp = CandidateDecisionAdapter.select_candidate([c1, c2])
    assert resp.selected_candidate_id == "cand-primary"
    assert resp.selected_candidate_patch == "print('primary')"
    assert resp.selected_by == "candidate_policy"
    assert resp.final_authority == "NexusVerifier"


def test_select_candidate_fallback_to_secondary() -> None:
    c1 = CandidateEnvelope(
        candidate_id="cand-primary-blocked",
        task_id="task-1",
        source="local",
        model="qwen-7b",
        role="primary_proposer",
        patch_protocol="anchored_edit",
        target_file="app.py",
        target_symbol="run",
        source_anchor_hash="hash-1",
        candidate_patch_hash="hash-2",
        evidence_refs=("ref-1",),
        risk_flags=("blocked_resource",),
        abstained=True,
        candidate_patch="print('primary')",
    )
    c2 = CandidateEnvelope(
        candidate_id="cand-secondary",
        task_id="task-1",
        source="local",
        model="ds-6.7b",
        role="secondary_proposer",
        patch_protocol="anchored_edit",
        target_file="app.py",
        target_symbol="run",
        source_anchor_hash="hash-1",
        candidate_patch_hash="hash-3",
        evidence_refs=("ref-1",),
        candidate_patch="print('secondary')",
    )

    resp = CandidateDecisionAdapter.select_candidate([c1, c2])
    assert resp.selected_candidate_id == "cand-secondary"
    assert resp.selected_candidate_patch == "print('secondary')"
    assert resp.selected_by == "candidate_policy_fallback"
    assert resp.final_authority == "NexusVerifier"


def test_select_candidate_none_available() -> None:
    resp = CandidateDecisionAdapter.select_candidate([])
    assert resp.selected_candidate_id == ""
    assert resp.selected_by == "none_available"
