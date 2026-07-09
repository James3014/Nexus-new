"""P8-C7: Audit Bundle Tests."""
from __future__ import annotations

import json
import os
import pytest


def test_bundle_exists():
    assert os.path.exists("artifacts/effect_reports/p8_c_independent_audit_bundle_v0.json")


def test_bundle_has_refs():
    with open("artifacts/effect_reports/p8_c_independent_audit_bundle_v0.json") as f:
        b = json.load(f)
    assert "c1_manifest_ref" in b
    assert "p7_final_seal_ref" in b


def test_safety_flags():
    with open("artifacts/effect_reports/p8_c_independent_audit_bundle_v0.json") as f:
        b = json.load(f)
    assert b["api_key_logged"] is False
    assert b["raw_prompt_logged"] is False
    assert b["patch_apply_invoked"] is False
    assert b["public_claim_allowed"] is False
    assert b["production_ready"] is False
    assert b["p2_hash_truth_required"] is True
    assert b["p4_verifier_required"] is True


def test_json_serializable():
    with open("artifacts/effect_reports/p8_c_independent_audit_bundle_v0.json") as f:
        json.load(f)
