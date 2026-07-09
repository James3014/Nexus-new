"""P8-A8: Evidence Bundle Tests."""
from __future__ import annotations

import json
import os
import pytest


def test_bundle_exists():
    assert os.path.exists("artifacts/effect_reports/p8_network_smoke_evidence_bundle_v0.json")


def test_bundle_has_all_reports():
    with open("artifacts/effect_reports/p8_network_smoke_evidence_bundle_v0.json") as f:
        b = json.load(f)
    for key in ["p8_a1_approval", "p8_a2_boundary", "p8_a3_redaction",
                 "p8_a4_receipt_schema", "p8_a5_dry_run", "p8_a6_smoke",
                 "p8_a7_validator", "p7_final_seal"]:
        assert key in b["artifacts"]


def test_safety_assertions():
    with open("artifacts/effect_reports/p8_network_smoke_evidence_bundle_v0.json") as f:
        b = json.load(f)
    s = b["safety_assertions"]
    assert s["api_key_logged"] is False
    assert s["raw_prompt_logged"] is False
    assert s["patch_apply_invoked"] is False
    assert s["public_claim_allowed"] is False
    assert s["production_ready"] is False
    assert s["actual_network_call_count"] == 0


def test_final_decision_blocked():
    with open("artifacts/effect_reports/p8_network_smoke_evidence_bundle_v0.json") as f:
        b = json.load(f)
    assert b["final_decision"] == "P8_CLOSED_BLOCKED_WITH_REASONS"
    assert b["smoke_status"] == "P8_A6_BLOCKED_PRECONDITION_FAILED"
