from __future__ import annotations

import os
import pytest
from nexus.services.local_heal.candidate_envelope import CandidateEnvelope
from nexus.services.local_heal.candidate_decision_adapter import CandidateDecisionAdapter


def test_candidate_decision_rejects_candidates_without_evidence_refs() -> None:
    # Validate envelope creation itself fails if evidence_refs is empty
    with pytest.raises(ValueError, match="evidence_refs must not be empty"):
        CandidateEnvelope(
            candidate_id="cand-1",
            task_id="task-1",
            source="local",
            model="qwen-7b",
            role="primary_proposer",
            patch_protocol="anchored_edit",
            target_file="app.py",
            target_symbol="run",
            source_anchor_hash="hash-1",
            candidate_patch_hash="hash-2",
            evidence_refs=(),
            candidate_patch="print('hello')",
        )


def test_ddtree_does_not_prune_only_verifier_pass_candidate(monkeypatch) -> None:
    monkeypatch.setenv("NEXUS_ENABLE_DDTREE", "1")
    
    # 建立一個有 invalid_dependency (通常會被 ddtree 剪掉)，但被標註為 verifier_pass 的 candidate
    c_pass = CandidateEnvelope(
        candidate_id="cand-pass-but-dependency-flagged",
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
        risk_flags=("invalid_dependency", "verifier_pass"),
        candidate_patch="print('hello')",
    )
    
    # 建立另一個被剪掉的 candidate (有 invalid_dependency，沒有 verifier_pass)
    c_pruned = CandidateEnvelope(
        candidate_id="cand-pruned",
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
        risk_flags=("invalid_dependency",),
        candidate_patch="print('pruned')",
    )

    resp = CandidateDecisionAdapter.select_candidate([c_pass, c_pruned])
    assert resp.selected_candidate_id == "cand-pass-but-dependency-flagged"
    assert any("pruned cand-pruned due to invalid dependency" in msg for msg in resp.ranking_trace)
    assert not any("pruned cand-pass-but-dependency-flagged" in msg for msg in resp.ranking_trace)


def test_autoreason_ranks_correctly_but_final_authority_remains_verifier(monkeypatch) -> None:
    monkeypatch.setenv("NEXUS_ENABLE_AUTOREASON", "1")
    
    c_secondary = CandidateEnvelope(
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
    
    c_primary = CandidateEnvelope(
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

    # 傳入時故意將 secondary 放在前面，測試 autoreason 能否正確排程並將 primary 移到前面
    resp = CandidateDecisionAdapter.select_candidate([c_secondary, c_primary])
    assert resp.selected_candidate_id == "cand-primary"
    assert resp.selected_by == "candidate_policy"
    assert resp.final_authority == "NexusVerifier"
    assert any("Autoreason ranked candidates by score" in msg for msg in resp.ranking_trace)
