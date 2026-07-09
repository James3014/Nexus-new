"""P6-G4: P3 Handoff Trace Tests."""
from __future__ import annotations

import json
import pytest
from nexus.services.local_heal.p6_p3_handoff_trace import generate_handoff_trace


def test_handoff_trace_one_row_per_case():
    trace = [{"case_id": "H01", "quota_scenario_budget_class": "healthy", "degradation_action": "keep_full_committee",
              "cloud_allowed": True, "local_allowed": True, "blocked_reasons": []}]
    handoff = generate_handoff_trace(trace)
    assert len(handoff) == 1
    assert handoff[0]["p6_can_override_p3_topology"] is False
    assert handoff[0]["p6_can_override_p4_verifier"] is False
    assert handoff[0]["p6_can_mark_solved"] is False
    assert handoff[0]["public_claim_allowed"] is False
    assert handoff[0]["production_ready"] is False


def test_rollback_severity_forces_fail_closed():
    trace = [{"case_id": "H01", "quota_scenario_budget_class": "healthy", "degradation_action": "keep_full_committee",
              "cloud_allowed": True, "local_allowed": True, "blocked_reasons": []}]
    handoff = generate_handoff_trace(trace, canary_severity="rollback")
    assert handoff[0]["p6_recommendation"] == "fail_closed"
    assert handoff[0]["fail_closed_recommendation"] is True
    assert "canary_severity_rollback" in handoff[0]["blocked_reasons"]


def test_no_p3_imports():
    import inspect
    import nexus.services.local_heal.p6_p3_handoff_trace as mod
    source = inspect.getsource(mod)
    assert "from nexus.services.local_heal.p3_" not in source
