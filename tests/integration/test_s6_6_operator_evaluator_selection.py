#!/usr/bin/env python3
"""Tests for S6.6 Operator Evaluator Selection"""

import json, sys
from pathlib import Path

NEXUS_ROOT = Path(__file__).resolve().parents[2]


def test_decision_request_exists():
    assert (NEXUS_ROOT / "docs/demo/s6_6_operator_decision_request.md").exists()


def test_input_form_exists():
    assert (NEXUS_ROOT / "docs/demo/s6_6_minimal_evaluator_input_form.md").exists()


def test_no_fake_evaluator():
    res_path = NEXUS_ROOT / "artifacts/demo/s6_6_evaluator_candidate_resolution.json"
    res = json.loads(res_path.read_text())
    assert res["resolution_status"] == "no_candidate_provided"
    assert res["evaluator_supplied"] == False


def test_no_fake_sent_status():
    ss_path = NEXUS_ROOT / "artifacts/demo/s6_6_invitation_send_status.json"
    ss = json.loads(ss_path.read_text())
    assert ss["invitation_sent"] == False


def test_no_fake_response():
    rt_path = NEXUS_ROOT / "artifacts/demo/s6_6_response_tracking_record.json"
    rt = json.loads(rt_path.read_text())
    assert rt["response_status"] == "not_applicable_invitation_not_sent"


def test_no_public_benchmark():
    report = (NEXUS_ROOT / "docs/demo/s6_6_operator_selection_blocker_packet.md").read_text()
    assert "public benchmark" not in report.lower() or "not" in report.lower()


def test_no_swe_bench():
    report = (NEXUS_ROOT / "docs/demo/s6_6_operator_selection_blocker_packet.md").read_text()
    assert "official swe-bench" not in report.lower() or "not" in report.lower()


def test_readiness_decision_blocked():
    decision = (NEXUS_ROOT / "docs/demo/s6_6_final_invitation_readiness_decision.md").read_text()
    assert "blocked_pending_operator_selection" in decision


if __name__ == "__main__":
    test_decision_request_exists()
    test_input_form_exists()
    test_no_fake_evaluator()
    test_no_fake_sent_status()
    test_no_fake_response()
    test_no_public_benchmark()
    test_no_swe_bench()
    test_readiness_decision_blocked()
    print("All S6.6 tests PASS")
