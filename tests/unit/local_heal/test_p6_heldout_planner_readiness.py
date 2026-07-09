"""P6-F2/F3/F4/F5: Tests for heldout planner, artifact, monitor adapter, readiness."""
from __future__ import annotations

import json
import os
import tempfile
import pytest
from nexus.services.local_heal.p6_heldout_planner import P6HeldoutPlanRow, plan_heldout_row
from nexus.services.local_heal.p6_heldout_monitor_adapter import P6HeldoutMonitorRow, convert_plan_row_to_monitor_row
from nexus.services.local_heal.p6_heldout_readiness import P6HeldoutReadinessDecision, evaluate_heldout_readiness


def test_plan_row_execution_not_allowed():
    plan = plan_heldout_row({"case_id": "t", "quota_scenario": "healthy", "expected_degradation_action": "keep_full_committee",
                              "expected_cloud_allowed": True, "expected_local_allowed": True, "expected_committee_allowed": True,
                              "expected_p5_allowed": True, "expected_candidate_count_min": 3, "expected_candidate_count_max": 10})
    assert plan.execution_allowed is False
    assert plan.public_claim_allowed is False


def test_monitor_row_synthetic():
    plan_row = {"case_id": "t", "quota_scenario": "healthy", "planned_degradation_action": "keep_full_committee",
                "planned_cloud_allowed": True, "planned_local_allowed": True, "planned_committee_allowed": True,
                "planned_p5_allowed": True, "planned_candidate_count_min": 3, "planned_candidate_count_max": 10,
                "verifier_required": True, "claim_gate_required": True}
    row = convert_plan_row_to_monitor_row(plan_row)
    assert row.evidence_kind == "heldout_plan_synthetic"
    assert row.real_execution_evidence is False
    assert row.public_claim_allowed is False


def test_readiness_dry_run_ready():
    decision = evaluate_heldout_readiness(
        fixture_valid=True, plan_artifact_present=True,
        monitor_rows=[{"dry_run_only": True, "public_claim_allowed": False, "production_ready": False,
                        "default_runtime_allowed": False, "verifier_required": True, "claim_gate_required": True}],
    )
    assert decision.decision == "P6_HELDOUT_DRY_RUN_READY"


def test_readiness_not_ready():
    decision = evaluate_heldout_readiness(fixture_valid=False, plan_artifact_present=False, monitor_rows=[])
    assert decision.decision == "P6_HELDOUT_NOT_READY"


def test_readiness_rollback_on_public_claim():
    decision = evaluate_heldout_readiness(
        fixture_valid=True, plan_artifact_present=True,
        monitor_rows=[{"dry_run_only": True, "public_claim_allowed": True, "production_ready": False,
                        "default_runtime_allowed": False, "verifier_required": True, "claim_gate_required": True}],
    )
    assert decision.decision == "P6_HELDOUT_ROLLBACK_REQUIRED"
