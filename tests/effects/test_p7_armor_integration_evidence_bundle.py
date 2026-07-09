"""P7-A6: Evidence Bundle Tests."""
from __future__ import annotations

import json
import os
import pytest


def test_bundle_exists():
    assert os.path.exists("artifacts/effect_reports/p7_armor_integration_evidence_bundle_v0.json")


def test_bundle_has_all_reports():
    with open("artifacts/effect_reports/p7_armor_integration_evidence_bundle_v0.json") as f:
        b = json.load(f)
    for key in ["p7_a1_manifest", "p7_a2_invariants", "p7_a3_synthetic_trace",
                 "p7_a4_receipts", "p7_a5_readiness", "p3_final_seal", "p6_final_seal"]:
        assert key in b["artifacts"]


def test_safety_assertions_all_safe():
    with open("artifacts/effect_reports/p7_armor_integration_evidence_bundle_v0.json") as f:
        b = json.load(f)
    for k, v in b["safety_assertions"].items():
        if k.endswith("_required"):
            assert v is True, f"{k} should be True"
        elif k.endswith("_only"):
            assert v is True, f"{k} should be True"
        else:
            assert v is False, f"{k} should be False"


def test_final_decision_present():
    with open("artifacts/effect_reports/p7_armor_integration_evidence_bundle_v0.json") as f:
        b = json.load(f)
    assert b["final_decision"] == "P7_CLOSED_ARMOR_SYNTHETIC_E2E_READY"


def test_json_serializable():
    with open("artifacts/effect_reports/p7_armor_integration_evidence_bundle_v0.json") as f:
        b = json.load(f)
    json.dumps(b)
