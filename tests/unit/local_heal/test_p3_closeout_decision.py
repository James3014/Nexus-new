from __future__ import annotations

import json
import pytest
from nexus.services.local_heal.p3_closeout_decision import (
    P3CloseoutDecision,
    compute_p3_closeout_decision,
    p3_closeout_decision_to_dict,
)


# ============================================================
# O7-1: valid synthetic trace closes as SYNTHETIC_PROVIDER_TRACE_READY
# ============================================================


def test_valid_synthetic_trace_closes():
    decision = compute_p3_closeout_decision(
        synthetic_trace_present=True,
        authority_coupling_present=True,
    )
    assert decision.decision == "P3_CLOSED_SYNTHETIC_PROVIDER_TRACE_READY"
    assert decision.final_public_claim_allowed is False
    assert decision.final_production_ready is False


# ============================================================
# O7-2: complete approval checklist allows HUMAN_APPROVED_NETWORK_SMOKE_READY
# ============================================================


def test_approval_checklist_allows_smoke_ready():
    decision = compute_p3_closeout_decision(
        synthetic_trace_present=True,
        authority_coupling_present=True,
        p6_advisory_contract_present=True,
        p6_advisory_only=True,
        human_approval_checklist_present=True,
    )
    assert decision.decision == "P3_CLOSED_HUMAN_APPROVED_NETWORK_SMOKE_READY"


# ============================================================
# O7-3: missing synthetic trace blocks
# ============================================================


def test_missing_synthetic_trace_blocks():
    decision = compute_p3_closeout_decision(
        synthetic_trace_present=False,
        authority_coupling_present=True,
    )
    assert decision.decision == "P3_CLOSED_BLOCKED"
    assert "synthetic_trace_missing" in decision.blocked_reasons


# ============================================================
# O7-4: missing authority coupling blocks
# ============================================================


def test_missing_authority_coupling_blocks():
    decision = compute_p3_closeout_decision(
        synthetic_trace_present=True,
        authority_coupling_present=False,
    )
    assert decision.decision == "P3_CLOSED_BLOCKED"
    assert "authority_coupling_missing" in decision.blocked_reasons


# ============================================================
# O7-5: real_provider_invoked=true triggers rollback
# ============================================================


def test_real_provider_triggers_rollback():
    decision = compute_p3_closeout_decision(
        synthetic_trace_present=True,
        authority_coupling_present=True,
        real_provider_invoked=True,
    )
    assert decision.decision == "P3_CLOSED_ROLLBACK_REQUIRED"
    assert "real_provider_invoked" in decision.blocked_reasons


# ============================================================
# O7-6: network_invoked=true triggers rollback
# ============================================================


def test_network_invoked_triggers_rollback():
    decision = compute_p3_closeout_decision(
        synthetic_trace_present=True,
        authority_coupling_present=True,
        network_invoked=True,
    )
    assert decision.decision == "P3_CLOSED_ROLLBACK_REQUIRED"
    assert "network_invoked" in decision.blocked_reasons


# ============================================================
# O7-7: api_key_used=true triggers rollback
# ============================================================


def test_api_key_used_triggers_rollback():
    decision = compute_p3_closeout_decision(
        synthetic_trace_present=True,
        authority_coupling_present=True,
        api_key_used=True,
    )
    assert decision.decision == "P3_CLOSED_ROLLBACK_REQUIRED"
    assert "api_key_used" in decision.blocked_reasons


# ============================================================
# O7-8: patch_apply_invoked=true triggers rollback
# ============================================================


def test_patch_apply_triggers_rollback():
    decision = compute_p3_closeout_decision(
        synthetic_trace_present=True,
        authority_coupling_present=True,
        patch_apply_invoked=True,
    )
    assert decision.decision == "P3_CLOSED_ROLLBACK_REQUIRED"
    assert "patch_apply_invoked" in decision.blocked_reasons


# ============================================================
# O7-9: runtime_behavior_changed=true triggers rollback
# ============================================================


def test_runtime_behavior_changed_triggers_rollback():
    decision = compute_p3_closeout_decision(
        synthetic_trace_present=True,
        authority_coupling_present=True,
        runtime_behavior_changed=True,
    )
    assert decision.decision == "P3_CLOSED_ROLLBACK_REQUIRED"
    assert "runtime_behavior_changed" in decision.blocked_reasons


# ============================================================
# O7-10: p2_hash_truth_required=false blocks/rollback
# ============================================================


def test_p2_hash_truth_not_required_blocks():
    decision = compute_p3_closeout_decision(
        synthetic_trace_present=True,
        authority_coupling_present=True,
        p2_hash_truth_required=False,
    )
    assert decision.decision == "P3_CLOSED_ROLLBACK_REQUIRED"
    assert "p2_hash_truth_not_required" in decision.blocked_reasons


# ============================================================
# O7-11: p4_full_verifier_required=false blocks/rollback
# ============================================================


def test_p4_verifier_not_required_blocks():
    decision = compute_p3_closeout_decision(
        synthetic_trace_present=True,
        authority_coupling_present=True,
        p4_full_verifier_required=False,
    )
    assert decision.decision == "P3_CLOSED_ROLLBACK_REQUIRED"
    assert "p4_full_verifier_not_required" in decision.blocked_reasons


# ============================================================
# O7-12: p4_claim_gate_required=false blocks/rollback
# ============================================================


def test_p4_claim_gate_not_required_blocks():
    decision = compute_p3_closeout_decision(
        synthetic_trace_present=True,
        authority_coupling_present=True,
        p4_claim_gate_required=False,
    )
    assert decision.decision == "P3_CLOSED_ROLLBACK_REQUIRED"
    assert "p4_claim_gate_not_required" in decision.blocked_reasons


# ============================================================
# O7-13: public_claim_allowed=true triggers rollback
# ============================================================


def test_public_claim_allowed_triggers_rollback():
    decision = compute_p3_closeout_decision(
        synthetic_trace_present=True,
        authority_coupling_present=True,
        final_public_claim_allowed=True,
    )
    assert decision.decision == "P3_CLOSED_ROLLBACK_REQUIRED"
    assert "public_claim_allowed" in decision.blocked_reasons


# ============================================================
# O7-14: production_ready=true triggers rollback
# ============================================================


def test_production_ready_triggers_rollback():
    decision = compute_p3_closeout_decision(
        synthetic_trace_present=True,
        authority_coupling_present=True,
        final_production_ready=True,
    )
    assert decision.decision == "P3_CLOSED_ROLLBACK_REQUIRED"
    assert "production_ready" in decision.blocked_reasons


# ============================================================
# O7-15: solved_by_p3=true triggers rollback
# ============================================================


def test_solved_by_p3_triggers_rollback():
    decision = compute_p3_closeout_decision(
        synthetic_trace_present=True,
        authority_coupling_present=True,
        solved_by_p3=True,
    )
    assert decision.decision == "P3_CLOSED_ROLLBACK_REQUIRED"
    assert "solved_by_p3" in decision.blocked_reasons


# ============================================================
# O7-16: JSON serialization works
# ============================================================


def test_json_serializable():
    decision = compute_p3_closeout_decision(
        synthetic_trace_present=True,
        authority_coupling_present=True,
    )
    d = p3_closeout_decision_to_dict(decision)
    assert isinstance(json.dumps(d), str)
