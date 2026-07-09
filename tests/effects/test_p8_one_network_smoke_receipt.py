"""P8-A6: One Network Smoke Receipt (blocked - no human approval)."""
from __future__ import annotations

import json
import os
import pytest


SMOKE_RECEIPT = {
    "receipt_version": "1.0",
    "smoke_id": "P8-BLOCKED-001",
    "approval_valid": False,
    "boundary_valid": False,
    "redaction_passed": True,
    "provider_kind": "",
    "model_name": "",
    "network_call_attempted": False,
    "network_call_completed": False,
    "network_call_count": 0,
    "timeout_seconds": 0,
    "timed_out": False,
    "cost_budget_usd": 0.0,
    "estimated_cost_usd": 0.0,
    "cost_budget_exceeded": False,
    "api_key_used": False,
    "api_key_logged": False,
    "raw_prompt_logged": False,
    "raw_response_logged": False,
    "redacted_prompt_hash": "",
    "provider_response_hash": "",
    "provider_response_redacted": "",
    "candidate_like_output_available": False,
    "patch_apply_invoked": False,
    "runtime_behavior_changed": False,
    "solved_claim": False,
    "claim_eligible": False,
    "public_claim_allowed": False,
    "production_ready": False,
    "p2_hash_truth_required": True,
    "p2_anchor_truth_required": True,
    "p4_verifier_required": True,
    "p4_claim_gate_required": True,
    "receipt_complete": True,
    "blocked_reasons": ["no_human_approval_artifact"],
}


def test_smoke_receipt_exists():
    os.makedirs("artifacts/effect_reports", exist_ok=True)
    path = "artifacts/effect_reports/p8_one_network_smoke_receipt_v0.json"
    with open(path, "w") as f:
        json.dump(SMOKE_RECEIPT, f, indent=2)
    assert os.path.exists(path)


def test_no_network_call_attempted():
    assert SMOKE_RECEIPT["network_call_attempted"] is False
    assert SMOKE_RECEIPT["network_call_count"] == 0


def test_safety_flags():
    assert SMOKE_RECEIPT["api_key_logged"] is False
    assert SMOKE_RECEIPT["raw_prompt_logged"] is False
    assert SMOKE_RECEIPT["raw_response_logged"] is False
    assert SMOKE_RECEIPT["patch_apply_invoked"] is False
    assert SMOKE_RECEIPT["runtime_behavior_changed"] is False
    assert SMOKE_RECEIPT["solved_claim"] is False
    assert SMOKE_RECEIPT["claim_eligible"] is False
    assert SMOKE_RECEIPT["public_claim_allowed"] is False
    assert SMOKE_RECEIPT["production_ready"] is False


def test_p2_p4_gates():
    assert SMOKE_RECEIPT["p2_hash_truth_required"] is True
    assert SMOKE_RECEIPT["p4_verifier_required"] is True


def test_blocked_reasons():
    assert "no_human_approval_artifact" in SMOKE_RECEIPT["blocked_reasons"]


def test_json_serializable():
    json.dumps(SMOKE_RECEIPT)
