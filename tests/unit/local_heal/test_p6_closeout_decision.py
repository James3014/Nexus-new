"""P6-H1+H2: Closeout Decision + Handoff Trace Tests."""
from __future__ import annotations

import json
import pytest
from nexus.services.local_heal.p6_closeout_decision import P6CloseoutDecision, evaluate_closeout
from nexus.services.local_heal.p6_p3_handoff_trace import generate_handoff_trace


GOOD = dict(g1_harness_passed=True, g2_receipt_artifact_present=True,
             g3_monitor_canary_passed=True, g4_handoff_trace_present=True,
             g3_summary={"real_execution_evidence_present": False, "public_claim_allowed": False, "production_ready": False})


def _with_summary(summary):
    """Return GOOD dict merged with a custom g3_summary."""
    d = dict(GOOD)
    d["g3_summary"] = summary
    return d


def test_valid_returns_dry_run_ready():
    d = evaluate_closeout(**GOOD)
    assert d.decision == "P6_CLOSED_HELDOUT_DRY_RUN_READY"
    assert d.final_public_claim_allowed is False
    assert d.final_production_ready is False


def test_missing_g1_blocks():
    d = evaluate_closeout(**{**GOOD, "g1_harness_passed": False})
    assert "g1_harness_failed" in d.blocked_reasons


def test_missing_g2_blocks():
    d = evaluate_closeout(**{**GOOD, "g2_receipt_artifact_present": False})
    assert "g2_receipt_artifact_missing" in d.blocked_reasons


def test_missing_g3_blocks():
    d = evaluate_closeout(**{**GOOD, "g3_monitor_canary_passed": False})
    assert "g3_monitor_canary_failed" in d.blocked_reasons


def test_missing_g4_blocks():
    d = evaluate_closeout(**{**GOOD, "g4_handoff_trace_present": False})
    assert "g4_handoff_trace_missing" in d.blocked_reasons


def test_real_evidence_triggers_rollback():
    d = evaluate_closeout(**_with_summary({"real_execution_evidence_present": True, "public_claim_allowed": False, "production_ready": False}))
    assert d.decision == "P6_CLOSED_ROLLBACK_REQUIRED"
    assert "real_execution_evidence_present" in d.blocked_reasons


def test_runtime_behavior_changed_triggers_rollback():
    d = evaluate_closeout(**GOOD, runtime_behavior_changed=True)
    assert d.decision == "P6_CLOSED_ROLLBACK_REQUIRED"
    assert "runtime_behavior_changed" in d.blocked_reasons


def test_public_claim_triggers_rollback():
    d = evaluate_closeout(**_with_summary({"real_execution_evidence_present": False, "public_claim_allowed": True, "production_ready": False}))
    assert d.decision == "P6_CLOSED_ROLLBACK_REQUIRED"
    assert "public_claim_allowed_detected" in d.blocked_reasons


def test_production_ready_triggers_rollback():
    d = evaluate_closeout(**_with_summary({"real_execution_evidence_present": False, "public_claim_allowed": False, "production_ready": True}))
    assert d.decision == "P6_CLOSED_ROLLBACK_REQUIRED"
    assert "production_ready_detected" in d.blocked_reasons


def test_not_all_dry_run_blocks():
    d = evaluate_closeout(**GOOD, all_rows_dry_run_only=False)
    assert "rows_not_all_dry_run_only" in d.blocked_reasons


def test_verifier_not_required_blocks():
    d = evaluate_closeout(**GOOD, all_rows_verifier_required=False)
    assert "verifier_not_required_for_all_rows" in d.blocked_reasons


def test_claim_gate_not_required_blocks():
    d = evaluate_closeout(**GOOD, all_rows_claim_gate_required=False)
    assert "claim_gate_not_required_for_all_rows" in d.blocked_reasons


def test_public_claim_not_false_blocks():
    d = evaluate_closeout(**GOOD, all_rows_public_claim_false=False)
    assert "public_claim_not_false_for_all_rows" in d.blocked_reasons


def test_production_ready_not_false_blocks():
    d = evaluate_closeout(**GOOD, all_rows_production_ready_false=False)
    assert "production_ready_not_false_for_all_rows" in d.blocked_reasons


def test_override_p3_triggers_rollback():
    d = evaluate_closeout(**GOOD, p6_overrode_p3_topology=True)
    assert d.decision == "P6_CLOSED_ROLLBACK_REQUIRED"
    assert "p6_overrode_p3_topology" in d.blocked_reasons


def test_override_p4_triggers_rollback():
    d = evaluate_closeout(**GOOD, p6_overrode_p4_verifier=True)
    assert d.decision == "P6_CLOSED_ROLLBACK_REQUIRED"
    assert "p6_overrode_p4_verifier" in d.blocked_reasons


def test_override_claim_gate_triggers_rollback():
    d = evaluate_closeout(**GOOD, p6_overrode_claim_gate=True)
    assert d.decision == "P6_CLOSED_ROLLBACK_REQUIRED"
    assert "p6_overrode_claim_gate" in d.blocked_reasons


def test_marked_solved_triggers_rollback():
    d = evaluate_closeout(**GOOD, p6_marked_solved=True)
    assert d.decision == "P6_CLOSED_ROLLBACK_REQUIRED"
    assert "p6_marked_solved" in d.blocked_reasons


def test_set_public_claim_triggers_rollback():
    d = evaluate_closeout(**GOOD, p6_set_public_claim_allowed=True)
    assert d.decision == "P6_CLOSED_ROLLBACK_REQUIRED"
    assert "p6_set_public_claim_allowed" in d.blocked_reasons


def test_multiple_violations_all_listed():
    d = evaluate_closeout(**GOOD, p6_marked_solved=True, p6_overrode_p3_topology=True, runtime_behavior_changed=True)
    assert d.decision == "P6_CLOSED_ROLLBACK_REQUIRED"
    assert "p6_marked_solved" in d.blocked_reasons
    assert "p6_overrode_p3_topology" in d.blocked_reasons
    assert "runtime_behavior_changed" in d.blocked_reasons


def test_json_serializable():
    d = evaluate_closeout(**GOOD)
    json.dumps({"decision": d.decision, "blocked_reasons": d.blocked_reasons})


# --- H2: Handoff trace tests ---

TRACE_ROW = {"case_id": "H01", "quota_scenario_budget_class": "healthy", "degradation_action": "keep_full_committee",
             "cloud_allowed": True, "local_allowed": True, "blocked_reasons": ["test_reason"]}


def test_normal_handoff_preserves_fields():
    h = generate_handoff_trace([TRACE_ROW], canary_severity="info")
    assert h[0]["p6_recommendation"] == "keep_full_committee"
    assert h[0]["cloud_disabled_recommendation"] is False
    assert h[0]["fail_closed_recommendation"] is False
    assert h[0]["blocked_reasons"] == ["test_reason"]


def test_rollback_forces_fail_closed():
    h = generate_handoff_trace([TRACE_ROW], canary_severity="rollback")
    assert h[0]["p6_recommendation"] == "fail_closed"
    assert h[0]["fail_closed_recommendation"] is True
    assert h[0]["cloud_disabled_recommendation"] is True


def test_rollback_preserves_case_id():
    h = generate_handoff_trace([TRACE_ROW], canary_severity="rollback")
    assert h[0]["case_id"] == "H01"


def test_rollback_preserves_quota_scenario():
    h = generate_handoff_trace([TRACE_ROW], canary_severity="rollback")
    assert h[0]["quota_scenario"] == "healthy"


def test_rollback_preserves_source_artifact():
    h = generate_handoff_trace([TRACE_ROW], canary_severity="rollback")
    assert "p6_heldout_monitor_canary_trace" in h[0]["source_artifact"]


def test_rollback_preserves_original_blocked_reasons():
    h = generate_handoff_trace([TRACE_ROW], canary_severity="rollback")
    assert "test_reason" in h[0]["blocked_reasons"]
    assert "canary_severity_rollback" in h[0]["blocked_reasons"]


def test_rollback_appends_canary_severity_rollback():
    h = generate_handoff_trace([TRACE_ROW], canary_severity="rollback")
    assert h[0]["blocked_reasons"][-1] == "canary_severity_rollback"


def test_rollback_has_cloud_disabled():
    h = generate_handoff_trace([TRACE_ROW], canary_severity="rollback")
    assert h[0]["cloud_disabled_recommendation"] is True


def test_rollback_public_claim_false():
    h = generate_handoff_trace([TRACE_ROW], canary_severity="rollback")
    assert h[0]["public_claim_allowed"] is False


def test_rollback_production_ready_false():
    h = generate_handoff_trace([TRACE_ROW], canary_severity="rollback")
    assert h[0]["production_ready"] is False


def test_rollback_cannot_override_p3():
    h = generate_handoff_trace([TRACE_ROW], canary_severity="rollback")
    assert h[0]["p6_can_override_p3_topology"] is False


def test_rollback_cannot_override_p4():
    h = generate_handoff_trace([TRACE_ROW], canary_severity="rollback")
    assert h[0]["p6_can_override_p4_verifier"] is False


def test_rollback_cannot_override_claim_gate():
    h = generate_handoff_trace([TRACE_ROW], canary_severity="rollback")
    assert h[0]["p6_can_override_claim_gate"] is False


def test_rollback_cannot_mark_solved():
    h = generate_handoff_trace([TRACE_ROW], canary_severity="rollback")
    assert h[0]["p6_can_mark_solved"] is False


def test_rollback_cannot_set_public_claim():
    h = generate_handoff_trace([TRACE_ROW], canary_severity="rollback")
    assert h[0]["p6_can_set_public_claim_allowed"] is False


def test_handoff_json_serializable():
    h = generate_handoff_trace([TRACE_ROW], canary_severity="rollback")
    json.dumps(h[0])
