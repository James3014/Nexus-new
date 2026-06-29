from __future__ import annotations

import os
import pytest
from nexus.services.local_heal.candidate_envelope import CandidateEnvelope
from nexus.services.local_heal.candidate_decision_adapter import CandidateDecisionAdapter


def test_three_arm_benchmark_scenarios(monkeypatch) -> None:
    # Set up candidates
    # 1. External Primary Candidate (has problem: flagged with invalid_dependency)
    c_external = CandidateEnvelope(
        candidate_id="cand-gemini-external",
        task_id="task-123",
        source="external",
        model="gemini-2.0",
        role="external_primary",
        patch_protocol="unified_diff",
        target_file="app.py",
        target_symbol="run",
        source_anchor_hash="hash-1",
        candidate_patch_hash="hash-2",
        evidence_refs=("ref-1",),
        risk_flags=("invalid_dependency",),
        candidate_patch="print('gemini-patch')",
    )

    # 2. Local Proposer Candidate (safe fallback)
    c_local_secondary = CandidateEnvelope(
        candidate_id="cand-qwen-local",
        task_id="task-123",
        source="local",
        model="qwen-7b",
        role="secondary_proposer",
        patch_protocol="anchored_edit",
        target_file="app.py",
        target_symbol="run",
        source_anchor_hash="hash-1",
        candidate_patch_hash="hash-3",
        evidence_refs=("ref-1",),
        risk_flags=(), # safe
        candidate_patch="print('local-patch')",
    )

    # ==========================================
    # Arm 1: External Bare (Direct Selection)
    # ==========================================
    # Bare directly selects Gemini external primary regardless of risk flags
    arm1_selected = c_external
    assert arm1_selected.candidate_id == "cand-gemini-external"

    # ==========================================
    # Arm 2: External + Nexus (Decision without local fallback)
    # ==========================================
    # Without local committee, only Gemini external exists
    resp_arm2 = CandidateDecisionAdapter.select_candidate([c_external])
    assert resp_arm2.selected_candidate_id == "cand-gemini-external"
    assert resp_arm2.selected_by == "external_primary_policy"

    # ==========================================
    # Arm 3: External + Nexus + Local Assist (Fallback via DDTree pruning)
    # ==========================================
    # Enable DDTree to prune invalid dependencies
    monkeypatch.setenv("NEXUS_ENABLE_DDTREE", "1")
    
    # Run decision adapter with both external and local fallback candidate
    resp_arm3 = CandidateDecisionAdapter.select_candidate([c_external, c_local_secondary])
    
    # Gemini external should be pruned by DDTree due to invalid_dependency,
    # leaving local qwen secondary proposer as the only valid selection.
    assert resp_arm3.selected_candidate_id == "cand-qwen-local"
    assert resp_arm3.selected_by == "candidate_policy_fallback"
    assert any("DDTree pruned cand-gemini-external" in msg for msg in resp_arm3.ranking_trace)
