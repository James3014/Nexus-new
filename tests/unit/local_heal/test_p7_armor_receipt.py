"""P7-A4: Armor Receipt Tests."""
from __future__ import annotations

import json
import pytest
from nexus.services.local_heal.p7_armor_receipt import build_armor_receipts


TRACE_ROW = {"trace_id": "T1", "p3_closed_status": "ok", "p6_closed_status": "ok",
             "p2_hash_truth_required": True, "p4_verifier_required": True,
             "p3_real_provider_invoked": False, "p3_network_invoked": False,
             "p3_api_key_used": False, "patch_apply_invoked": False,
             "runtime_behavior_changed": False, "solved_claim": False,
             "claim_eligible": False, "public_claim_allowed": False,
             "production_ready": False}


def test_valid_row_produces_complete_receipt():
    receipts = build_armor_receipts([TRACE_ROW])
    assert len(receipts) == 1
    assert receipts[0]["receipt_complete"] is True
    assert receipts[0]["invariant_passed"] is True


def test_provider_invoked_blocks():
    r = dict(TRACE_ROW, p3_real_provider_invoked=True)
    receipts = build_armor_receipts([r])
    assert receipts[0]["receipt_complete"] is False
    assert "provider_invoked" in receipts[0]["blocked_reasons"]


def test_public_claim_blocks():
    r = dict(TRACE_ROW, public_claim_allowed=True)
    receipts = build_armor_receipts([r])
    assert "public_claim_allowed" in receipts[0]["blocked_reasons"]


def test_production_ready_blocks():
    r = dict(TRACE_ROW, production_ready=True)
    receipts = build_armor_receipts([r])
    assert "production_ready" in receipts[0]["blocked_reasons"]


def test_missing_p2_hash_blocks():
    r = dict(TRACE_ROW, p2_hash_truth_required=False)
    receipts = build_armor_receipts([r])
    assert "p2_hash_truth_missing" in receipts[0]["blocked_reasons"]


def test_json_serializable():
    receipts = build_armor_receipts([TRACE_ROW])
    json.dumps(receipts[0])
