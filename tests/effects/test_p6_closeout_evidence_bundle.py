"""P6-G6: Closeout Evidence Bundle Tests."""
from __future__ import annotations

import json
import os
import pytest


def test_bundle_exists():
    assert os.path.exists("artifacts/effect_reports/p6_closeout_evidence_bundle_v0.json")


def test_bundle_has_all_artifacts():
    with open("artifacts/effect_reports/p6_closeout_evidence_bundle_v0.json") as f:
        bundle = json.load(f)
    for key in ["g1_harness_report", "g2_dry_run_receipts", "g3_monitor_canary_trace",
                 "g4_p3_handoff_trace", "g5_closeout_decision", "g7_runbook_drill"]:
        assert key in bundle["artifacts"]


def test_safety_assertions_all_safe():
    with open("artifacts/effect_reports/p6_closeout_evidence_bundle_v0.json") as f:
        bundle = json.load(f)
    for k, v in bundle["safety_assertions"].items():
        assert v is False, f"{k} should be False"


def test_public_claim_false():
    with open("artifacts/effect_reports/p6_closeout_evidence_bundle_v0.json") as f:
        bundle = json.load(f)
    assert bundle["final_public_claim_allowed"] is False
    assert bundle["final_production_ready"] is False
