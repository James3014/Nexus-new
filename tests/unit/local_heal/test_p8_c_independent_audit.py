"""P8-C1→C6: Independent Audit Tests."""
from __future__ import annotations

import json
import os
import tempfile
import pytest
from nexus.services.local_heal.p8_c_smoke_evidence_manifest import P8CSmokeEvidenceManifest, load_smoke_manifest
from nexus.services.local_heal.p8_c_receipt_auditor import P8CReceiptAuditResult, audit_smoke_receipt
from nexus.services.local_heal.p8_c_redaction_auditor import P8CRedactionAuditResult, audit_redaction
from nexus.services.local_heal.p8_c_call_budget_auditor import P8CCallBudgetAuditResult, audit_call_budget
from nexus.services.local_heal.p8_c_authority_auditor import P8CAuthorityAuditResult, audit_authority
from nexus.services.local_heal.p8_c_p9_readiness import P8CP9ReadinessDecision, evaluate_p9_readiness

GOOD_RECEIPT = {
    "receipt_version": "1.0", "smoke_id": "T1", "network_call_attempted": True,
    "network_call_completed": True, "network_call_count": 1, "timed_out": False,
    "timeout_seconds": 15, "cost_budget_usd": 0.50, "estimated_cost_usd": 0.01,
    "cost_budget_exceeded": False, "retry_attempted": False, "streaming_used": False,
    "tool_call_used": False, "api_key_used": True, "api_key_logged": False,
    "raw_prompt_logged": False, "raw_response_logged": False,
    "redacted_prompt_hash": "abc123", "provider_response_hash": "def456",
    "patch_apply_invoked": False, "runtime_behavior_changed": False,
    "solved_claim": False, "claim_eligible": False, "public_claim_allowed": False,
    "production_ready": False, "p2_hash_truth_required": True, "p2_anchor_truth_required": True,
    "p4_verifier_required": True, "p4_claim_gate_required": True, "receipt_complete": True,
}

# C1
def test_manifest_missing_blocks():
    with tempfile.TemporaryDirectory() as d:
        m = load_smoke_manifest(d)
        assert m.manifest_complete is False

# C2
def test_receipt_audit_valid():
    r = audit_smoke_receipt(GOOD_RECEIPT)
    assert r.receipt_structurally_valid is True

def test_receipt_count_exceeded():
    r = audit_smoke_receipt({**GOOD_RECEIPT, "network_call_count": 2})
    assert "network_call_count_exceeded" in r.blocked_reasons

def test_receipt_api_key_logged():
    r = audit_smoke_receipt({**GOOD_RECEIPT, "api_key_logged": True})
    assert "api_key_logged" in r.blocked_reasons

def test_receipt_solved_claim():
    r = audit_smoke_receipt({**GOOD_RECEIPT, "solved_claim": True})
    assert "solved_claim" in r.blocked_reasons

def test_receipt_public_claim():
    r = audit_smoke_receipt({**GOOD_RECEIPT, "public_claim_allowed": True})
    assert "public_claim_allowed" in r.blocked_reasons

# C3
def test_redaction_safe():
    r = audit_redaction({"prompt_capsule": True, "receipt": True,
                          "redacted_prompt_hash": "abc", "network_call_completed": True,
                          "provider_response_hash": "def"})
    assert r.redaction_audit_passed is True

def test_redaction_secret_detected():
    r = audit_redaction({"prompt_capsule": True, "redacted_prompt_hash": "abc",
                          "content": "api_key=sk-real1234567890abcdef"})
    assert r.redaction_audit_passed is False

def test_redaction_raw_prompt_logged():
    r = audit_redaction({"redacted_prompt_hash": "abc", "raw_prompt_logged": True})
    assert "raw_prompt_logged" in r.blocked_reasons

# C4
def test_call_budget_valid():
    r = audit_call_budget(GOOD_RECEIPT)
    assert r.call_budget_audit_passed is True
    assert r.rollback_required is False

def test_call_budget_retry_rollback():
    r = audit_call_budget({**GOOD_RECEIPT, "retry_attempted": True})
    assert r.rollback_required is True

def test_call_budget_cost_exceeded():
    r = audit_call_budget({**GOOD_RECEIPT, "cost_budget_exceeded": True})
    assert "cost_budget_exceeded" in r.blocked_reasons

# C5
def test_authority_valid():
    r = audit_authority(GOOD_RECEIPT)
    assert r.authority_audit_passed is True

def test_authority_patch_apply():
    r = audit_authority({**GOOD_RECEIPT, "patch_apply_invoked": True})
    assert r.rollback_required is True

def test_authority_production_ready():
    r = audit_authority({**GOOD_RECEIPT, "production_ready": True})
    assert r.rollback_required is True

# C6
def test_p9_readiness_valid():
    d = evaluate_p9_readiness(
        manifest_complete=True, receipt_structurally_valid=True,
        redaction_audit_passed=True, call_budget_audit_passed=True,
        authority_audit_passed=True, smoke_completed=True, network_call_count=1,
    )
    assert d.decision == "P8_C_AUDIT_PASSED_P9_READY"
    assert d.p9_may_start is True

def test_p9_readiness_missing_manifest():
    d = evaluate_p9_readiness(
        manifest_complete=False, receipt_structurally_valid=True,
        redaction_audit_passed=True, call_budget_audit_passed=True,
        authority_audit_passed=True, smoke_completed=True, network_call_count=1,
    )
    assert "manifest_incomplete" in d.blocked_reasons

def test_p9_readiness_no_smoke():
    d = evaluate_p9_readiness(
        manifest_complete=True, receipt_structurally_valid=True,
        redaction_audit_passed=True, call_budget_audit_passed=True,
        authority_audit_passed=True, smoke_completed=False, network_call_count=0,
    )
    assert d.p9_may_start is False

def test_json_serializable():
    d = evaluate_p9_readiness(
        manifest_complete=True, receipt_structurally_valid=True,
        redaction_audit_passed=True, call_budget_audit_passed=True,
        authority_audit_passed=True, smoke_completed=True, network_call_count=1,
    )
    json.dumps({"decision": d.decision, "blocked_reasons": d.blocked_reasons})
