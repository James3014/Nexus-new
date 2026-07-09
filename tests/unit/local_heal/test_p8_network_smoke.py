"""P8-A1→A5+A7: Combined P8 tests."""
from __future__ import annotations

import json
import pytest
from nexus.services.local_heal.p8_network_smoke_approval import evaluate_approval
from nexus.services.local_heal.p8_network_smoke_boundary import build_boundary
from nexus.services.local_heal.p8_redaction_guard import redact_prompt
from nexus.services.local_heal.p8_network_smoke_receipt import validate_smoke_receipt
from nexus.services.local_heal.p8_network_smoke_executor import dry_run_smoke
from nexus.services.local_heal.p8_smoke_result_validator import validate_smoke_result

GOOD_APPROVAL = dict(human_approved=True, approver="test", provider_kind="openai",
                     model_name="gpt-4o-mini", max_network_calls=1, max_cost_usd=0.50,
                     timeout_seconds=15)

# A1 tests
def test_valid_approval():
    a = evaluate_approval(**GOOD_APPROVAL)
    assert a.approval_valid is True

def test_approval_human_approved_false():
    a = evaluate_approval(**{**GOOD_APPROVAL, "human_approved": False})
    assert a.approval_valid is False
    assert "human_approved_false" in a.blocked_reasons

def test_approval_max_calls_not_1():
    a = evaluate_approval(**{**GOOD_APPROVAL, "max_network_calls": 2})
    assert "max_network_calls_not_1" in a.blocked_reasons

def test_approval_cost_too_high():
    a = evaluate_approval(**{**GOOD_APPROVAL, "max_cost_usd": 2.00})
    assert "cost_budget_invalid" in a.blocked_reasons

def test_approval_timeout_too_long():
    a = evaluate_approval(**{**GOOD_APPROVAL, "timeout_seconds": 60})
    assert "timeout_invalid" in a.blocked_reasons

def test_approval_api_key_logging_blocked():
    a = evaluate_approval(**{**GOOD_APPROVAL, "api_key_logging_allowed": True})
    assert "api_key_logging_allowed" in a.blocked_reasons

def test_approval_patch_apply_blocked():
    a = evaluate_approval(**{**GOOD_APPROVAL, "patch_apply_allowed": True})
    assert "patch_apply_allowed" in a.blocked_reasons

def test_approval_public_claim_blocked():
    a = evaluate_approval(**{**GOOD_APPROVAL, "public_claim_allowed": True})
    assert "public_claim_allowed" in a.blocked_reasons

def test_approval_production_ready_blocked():
    a = evaluate_approval(**{**GOOD_APPROVAL, "production_ready": True})
    assert "production_ready" in a.blocked_reasons

# A2 tests
def test_valid_boundary():
    b = build_boundary(approval_valid=True, provider_kind="openai", model_name="gpt-4o-mini")
    assert b.boundary_valid is True

def test_boundary_invalid_approval():
    b = build_boundary(approval_valid=False)
    assert b.boundary_valid is False
    assert "approval_invalid" in b.blocked_reasons

def test_boundary_retry_blocked():
    b = build_boundary(approval_valid=True, retry_allowed=True)
    assert "retry_not_allowed" in b.blocked_reasons

def test_boundary_streaming_blocked():
    b = build_boundary(approval_valid=True, streaming_allowed=True)
    assert "streaming_not_allowed" in b.blocked_reasons

# A3 tests
def test_redact_safe_prompt():
    r = redact_prompt("What is 2+2?")
    assert r.redaction_passed is True
    assert r.secrets_detected == 0

def test_redact_api_key():
    r = redact_prompt("api_key=sk-1234567890abcdef1234567890abcdef")
    assert r.secrets_detected > 0
    assert "REDACTED" in r.redacted_prompt

def test_redact_bearer():
    r = redact_prompt("Authorization: Bearer abc123def456ghi789")
    assert r.secrets_detected > 0

# A4 tests
def test_valid_receipt():
    ok, blocked = validate_smoke_receipt({
        "network_call_count": 1, "api_key_logged": False, "raw_prompt_logged": False,
        "raw_response_logged": False, "patch_apply_invoked": False,
        "runtime_behavior_changed": False, "solved_claim": False,
        "public_claim_allowed": False, "production_ready": False,
        "p2_hash_truth_required": True, "p4_verifier_required": True,
    })
    assert ok is True

def test_receipt_count_exceeded():
    ok, blocked = validate_smoke_receipt({"network_call_count": 2})
    assert ok is False
    assert "network_call_count_exceeded" in blocked

def test_receipt_public_claim_blocks():
    ok, blocked = validate_smoke_receipt({"public_claim_allowed": True})
    assert "public_claim_allowed" in blocked

# A5 tests
def test_dry_run_valid():
    r = dry_run_smoke(approval_valid=True, boundary_valid=True, redaction_passed=True)
    assert r.dry_run is True
    assert r.execution_allowed is True
    assert r.network_call_attempted is False
    assert r.network_call_count == 0

def test_dry_run_invalid_approval():
    r = dry_run_smoke(approval_valid=False, boundary_valid=True, redaction_passed=True)
    assert r.execution_allowed is False

# A7 tests
def test_validate_empty():
    v = validate_smoke_result({})
    assert v.smoke_valid is False
    assert v.smoke_receipt_present is False

def test_validate_valid_receipt():
    v = validate_smoke_result({
        "network_call_attempted": True, "network_call_completed": True,
        "network_call_count": 1, "api_key_logged": False,
        "raw_prompt_logged": False, "raw_response_logged": False,
        "patch_apply_invoked": False, "runtime_behavior_changed": False,
        "solved_claim": False, "public_claim_allowed": False,
        "production_ready": False, "p2_hash_truth_required": True,
        "p4_verifier_required": True,
    })
    assert v.smoke_valid is True

def test_validate_solved_claim_blocks():
    v = validate_smoke_result({"solved_claim": True})
    assert "solved_claim" in v.blocked_reasons

def test_json_serializable():
    a = evaluate_approval(**GOOD_APPROVAL)
    json.dumps({"approval_valid": a.approval_valid})
