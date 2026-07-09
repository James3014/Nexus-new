"""P6-G5: Closeout Decision Tests."""
from __future__ import annotations

import json
import pytest
from nexus.services.local_heal.p6_closeout_decision import P6CloseoutDecision, evaluate_closeout


def test_valid_package_closes_dry_run_ready():
    decision = evaluate_closeout(
        g1_harness_passed=True, g2_receipt_artifact_present=True,
        g3_monitor_canary_passed=True, g4_handoff_trace_present=True,
        g3_summary={"real_execution_evidence_present": False, "public_claim_allowed": False, "production_ready": False},
    )
    assert decision.decision == "P6_CLOSED_HELDOUT_DRY_RUN_READY"
    assert decision.final_public_claim_allowed is False
    assert decision.final_production_ready is False


def test_missing_g2_blocks():
    decision = evaluate_closeout(g1_harness_passed=True, g2_receipt_artifact_present=False,
                                  g3_monitor_canary_passed=True, g4_handoff_trace_present=True)
    assert decision.decision == "P6_CLOSED_BLOCKED"
    assert "g2_receipt_artifact_missing" in decision.blocked_reasons


def test_real_evidence_triggers_rollback():
    decision = evaluate_closeout(g1_harness_passed=True, g2_receipt_artifact_present=True,
                                  g3_monitor_canary_passed=True, g4_handoff_trace_present=True,
                                  g3_summary={"real_execution_evidence_present": True, "public_claim_allowed": False, "production_ready": False})
    assert decision.decision == "P6_CLOSED_ROLLBACK_REQUIRED"
    assert "real_execution_evidence_present" in decision.blocked_reasons


def test_public_claim_triggers_rollback():
    decision = evaluate_closeout(g1_harness_passed=True, g2_receipt_artifact_present=True,
                                  g3_monitor_canary_passed=True, g4_handoff_trace_present=True,
                                  g3_summary={"real_execution_evidence_present": False, "public_claim_allowed": True, "production_ready": False})
    assert decision.decision == "P6_CLOSED_ROLLBACK_REQUIRED"
    assert "public_claim_allowed_detected" in decision.blocked_reasons


def test_json_serializable():
    decision = evaluate_closeout(g1_harness_passed=True, g2_receipt_artifact_present=True,
                                  g3_monitor_canary_passed=True, g4_handoff_trace_present=True,
                                  g3_summary={"real_execution_evidence_present": False, "public_claim_allowed": False, "production_ready": False})
    d = {"decision": decision.decision, "final_public_claim_allowed": decision.final_public_claim_allowed}
    json_str = json.dumps(d)
    assert len(json_str) > 0
