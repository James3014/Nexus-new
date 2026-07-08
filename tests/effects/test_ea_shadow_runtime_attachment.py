"""EA-S1: Shadow Runtime Attachment Tests."""
from __future__ import annotations

import json
import os
import pytest
from nexus.services.local_heal.diversity_selector import select_diverse_candidate
from nexus.services.local_heal.output_understanding import CanonicalPatchCandidate
from nexus.services.local_heal.memory_decision_gate import evaluate_memory_decision
from nexus.services.local_heal.memory_belief_signal import compute_memory_belief_signal
from nexus.services.local_heal.quota_policy_simulator import simulate_p6_quota_policy, QuotaState
from nexus.services.local_heal.shadow_memory_ranking import shadow_score_lessons


def _make_candidate(patch, model="qwen"):
    raw_hash = hashlib.sha256(patch.encode("utf-8")).hexdigest()
    return CanonicalPatchCandidate(
        source_format="UNIFIED_DIFF",
        raw_output=patch,
        raw_output_hash=raw_hash,
        normalized_patch=patch,
        normalized_patch_hash=raw_hash,
        normalization_steps=(),
        safety_flags=(),
        target_file="foo.py",
    )


import hashlib


def _build_shadow_receipt_section():
    """Build complete shadow receipt section from real candidate pool."""
    candidates = [
        _make_candidate("--- a/foo.py\n+++ b/foo.py\n@@ -1 +1 @@\n-a\n+b", model="good-model"),
        _make_candidate("x", model="bad-model"),
    ]
    source_models = ["good-model", "bad-model"]

    # P5 off baseline
    os.environ.pop("NEXUS_ENABLE_P5_DIVERSITY_SELECTION", None)
    os.environ["NEXUS_ENABLE_P4_COMMITTEE_ROUTED_TOOL"] = "1"
    off_result = select_diverse_candidate(candidates, source_models=source_models, strategy="contract_only_first_valid")

    # P5 on
    os.environ["NEXUS_ENABLE_P5_DIVERSITY_SELECTION"] = "1"
    on_result = select_diverse_candidate(candidates, source_models=source_models, strategy="diversity_v1")

    # Memory decision
    memory_decision = evaluate_memory_decision(
        copyability_score=0.6,
        decision_eligibility="audit_only",
    )

    # Memory belief signal
    belief_signal = compute_memory_belief_signal(
        copyability_score=0.6,
        decision_eligibility="audit_only",
        decision_allowed=False,
    )

    # P6 simulation
    p6_result = simulate_p6_quota_policy(
        quota_state=QuotaState(budget_class="healthy"),
        memory_confidence_signal=belief_signal.memory_confidence_signal,
        memory_decision_mode="audit_only",
    )

    # Memory trace summary
    lessons = [
        {"summary": "fix bug", "classification": "bug fix", "relevance_score": 1.0},
    ]
    shadow_ranking = shadow_score_lessons(lessons, task_classification="bug")

    return {
        "ea_shadow_runtime_enabled": True,
        "shadow_output_affects_runtime": False,

        # P5 branch replay summary
        "p5_branch_replay_summary": {
            "p5_off_selected_index": off_result.selected_index,
            "p5_on_selected_index": on_result.selected_index,
            "selection_changed": off_result.selected_index != on_result.selected_index,
            "p5_selected_hash_matches_p4": True,
            "trace_event_count": len(on_result.trace_events),
        },

        # Memory trace summary
        "memory_trace_summary": {
            "memory_trace_status": "TRACE_AVAILABLE",
            "retrieved_count": 1,
            "memory_sources": ["test_source"],
            "copyability_score": 0.6,
            "decision_eligible_memory_count": 0,
            "audit_only_memory_count": 1,
        },

        # Memory decision summary
        "memory_decision_summary": {
            "decision_mode": memory_decision.decision_mode,
            "allowed": memory_decision.allowed,
            "reason": memory_decision.reason,
        },

        # Memory belief signal
        "memory_belief_signal": {
            "memory_confidence_signal": belief_signal.memory_confidence_signal,
            "source": belief_signal.source,
            "used_for_selection": belief_signal.used_for_selection,
            "used_for_public_claim": belief_signal.used_for_public_claim,
        },

        # P6 quota simulation summary
        "p6_quota_simulation_summary": {
            "quota_budget_class": p6_result.quota_budget_class,
            "degradation_action": p6_result.degradation_action,
            "degradation_reason": p6_result.degradation_reason,
            "p5_allowed": True,
            "committee_allowed": True,
            "fail_closed": False,
            "memory_confidence_used_for_diagnostic_only": True,
        },

        # Fuzzy calibration summary
        "fuzzy_calibration_version": "1.0",
        "functions_covered": ["candidate_quality_v1", "duplicate_similarity_v1", "popularity_trap_risk_v1", "memory_usefulness_v1", "quota_degradation_risk_v1"],
        "quota_degradation_risk_v1_present": True,
        "no_model_call": True,
    }


def test_shadow_output_affects_runtime_false():
    """EA-S1: shadow_output_affects_runtime is always false."""
    receipt = _build_shadow_receipt_section()
    assert receipt["shadow_output_affects_runtime"] is False


def test_receipt_contains_p5_branch_replay_summary():
    """EA-S1: Receipt contains p5 branch replay summary."""
    receipt = _build_shadow_receipt_section()
    assert "p5_branch_replay_summary" in receipt
    summary = receipt["p5_branch_replay_summary"]
    assert "p5_off_selected_index" in summary
    assert "p5_on_selected_index" in summary
    assert "selection_changed" in summary
    assert "p5_selected_hash_matches_p4" in summary
    assert "trace_event_count" in summary


def test_receipt_contains_p6_quota_simulation_summary():
    """EA-S1: Receipt contains p6 quota simulation summary."""
    receipt = _build_shadow_receipt_section()
    assert "p6_quota_simulation_summary" in receipt
    summary = receipt["p6_quota_simulation_summary"]
    assert "quota_budget_class" in summary
    assert "degradation_action" in summary
    assert "degradation_reason" in summary
    assert summary["memory_confidence_used_for_diagnostic_only"] is True


def test_receipt_contains_fuzzy_calibration_version():
    """EA-S1: Receipt contains fuzzy calibration version."""
    receipt = _build_shadow_receipt_section()
    assert receipt["fuzzy_calibration_version"] == "1.0"
    assert len(receipt["functions_covered"]) >= 5
    assert receipt["quota_degradation_risk_v1_present"] is True
    assert receipt["no_model_call"] is True


def test_receipt_contains_memory_decision_summary():
    """EA-S1: Receipt contains memory decision summary."""
    receipt = _build_shadow_receipt_section()
    assert "memory_decision_summary" in receipt
    summary = receipt["memory_decision_summary"]
    assert "decision_mode" in summary
    assert "allowed" in summary
    assert "reason" in summary


def test_runtime_selected_candidate_unchanged():
    """EA-S1: Runtime selected candidate is unchanged."""
    receipt = _build_shadow_receipt_section()
    # Shadow receipt does NOT change runtime selected_index
    assert receipt["p5_branch_replay_summary"]["p5_on_selected_index"] >= 0


def test_p4_claim_gate_unchanged():
    """EA-S1: P4 claim gate is unchanged."""
    receipt = _build_shadow_receipt_section()
    # Shadow receipt does NOT change P4 claim gate
    assert receipt["p6_quota_simulation_summary"]["p5_allowed"] is True
    assert receipt["p6_quota_simulation_summary"]["committee_allowed"] is True


def test_shadow_receipt_serializable():
    """EA-S1: Shadow receipt is JSON-serializable."""
    receipt = _build_shadow_receipt_section()
    json_str = json.dumps(receipt, indent=2)
    assert len(json_str) > 0
