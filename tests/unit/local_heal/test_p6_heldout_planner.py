"""P6-F2: Heldout Case Planner Tests."""
from __future__ import annotations

import json
import pytest
from nexus.services.local_heal.p6_heldout_planner import P6HeldoutPlanRow, plan_heldout_row


def test_valid_fixture_row_produces_plan_row():
    row = {"case_id": "H01", "task_difficulty": "easy", "quota_scenario": "healthy",
           "expected_degradation_action": "keep_full_committee", "expected_cloud_allowed": True,
           "expected_local_allowed": True, "expected_committee_allowed": True, "expected_p5_allowed": True,
           "expected_candidate_count_min": 3, "expected_candidate_count_max": 10}
    plan = plan_heldout_row(row)
    assert plan.case_id == "H01"
    assert plan.execution_allowed is False
    assert plan.dry_run_only is True


def test_all_rows_execution_not_allowed():
    scenarios = ["healthy", "constrained", "exhausted_local_available", "exhausted_local_unavailable", "unknown"]
    for qs in scenarios:
        plan = plan_heldout_row({"case_id": "t", "quota_scenario": qs, "expected_degradation_action": "keep_full_committee",
                                  "expected_cloud_allowed": True, "expected_local_allowed": True, "expected_committee_allowed": True,
                                  "expected_p5_allowed": True, "expected_candidate_count_min": 3, "expected_candidate_count_max": 10})
        assert plan.execution_allowed is False
        assert plan.public_claim_allowed is False
        assert plan.production_ready is False
        assert plan.default_runtime_allowed is False


def test_unknown_keep_full_committee_blocked():
    plan = plan_heldout_row({"case_id": "t", "quota_scenario": "unknown", "expected_degradation_action": "keep_full_committee",
                              "expected_cloud_allowed": True, "expected_local_allowed": True, "expected_committee_allowed": True,
                              "expected_p5_allowed": True, "expected_candidate_count_min": 3, "expected_candidate_count_max": 10})
    assert plan.execution_allowed is False
    assert "unknown_quota_keep_full_committee" in plan.blocked_reasons


def test_constrained_min_below_2_blocked():
    plan = plan_heldout_row({"case_id": "t", "quota_scenario": "constrained", "expected_degradation_action": "reduce_candidate_count",
                              "expected_cloud_allowed": True, "expected_local_allowed": True, "expected_committee_allowed": True,
                              "expected_p5_allowed": True, "expected_candidate_count_min": 1, "expected_candidate_count_max": 10})
    assert plan.execution_allowed is False
    assert "constrained_candidate_count_below_2" in plan.blocked_reasons


def test_json_serializable():
    plan = plan_heldout_row({"case_id": "t", "quota_scenario": "healthy", "expected_degradation_action": "keep_full_committee",
                              "expected_cloud_allowed": True, "expected_local_allowed": True, "expected_committee_allowed": True,
                              "expected_p5_allowed": True, "expected_candidate_count_min": 3, "expected_candidate_count_max": 10})
    d = {"case_id": plan.case_id, "execution_allowed": plan.execution_allowed}
    json_str = json.dumps(d)
    assert len(json_str) > 0
