"""P6-G1: Heldout Dry-Run Harness Tests."""
from __future__ import annotations

import json
import pytest
from nexus.services.local_heal.p6_heldout_dry_run_harness import P6HeldoutDryRunReceipt, run_heldout_dry_run


def _valid_row(i):
    difficulty = ["easy", "medium", "hard"][i % 3]
    scenario = ["healthy", "constrained", "exhausted_local_available", "exhausted_local_unavailable", "unknown"][i % 5]
    if scenario == "unknown":
        action, cloud, local, committee, p5 = "fail_closed", False, False, False, False
    elif scenario == "exhausted_local_unavailable":
        action, cloud, local, committee, p5 = "fail_closed", False, False, False, False
    elif scenario == "exhausted_local_available":
        action, cloud, local, committee, p5 = "local_only", False, True, False, True
    elif scenario == "constrained":
        action, cloud, local, committee, p5 = "reduce_candidate_count", True, True, True, True
    else:
        action, cloud, local, committee, p5 = "keep_full_committee", True, True, True, True
    return {
        "case_id": f"H{i+1:02d}", "task_difficulty": difficulty, "quota_scenario": scenario,
        "quota_known": scenario != "unknown", "local_available": scenario != "exhausted_local_unavailable",
        "requested_candidate_count": 5, "expected_degradation_action": action,
        "expected_cloud_allowed": cloud, "expected_local_allowed": local,
        "expected_committee_allowed": committee, "expected_p5_allowed": p5,
        "expected_candidate_count_min": 3 if action == "keep_full_committee" else (2 if action == "reduce_candidate_count" else 1),
        "expected_candidate_count_max": 10 if action == "keep_full_committee" else (9 if action == "reduce_candidate_count" else 1),
        "verifier_required": True, "claim_gate_required": True, "public_claim_allowed": False,
        "default_runtime_allowed": False, "production_ready": False,
        "expected_result_class": "pass" if action != "fail_closed" else "fail_closed", "notes": f"{difficulty} {scenario}",
    }


def _valid_fixture():
    return [_valid_row(i) for i in range(45)]


def test_harness_loads_valid_fixture():
    result = run_heldout_dry_run(_valid_fixture())
    assert result["gate_passed"] is True
    assert result["total_rows"] == 45


def test_harness_rejects_invalid_fixture():
    result = run_heldout_dry_run([{"case_id": "X", "task_difficulty": "easy", "quota_scenario": "unknown",
                                   "expected_degradation_action": "keep_full_committee", "expected_cloud_allowed": True,
                                   "expected_local_allowed": True, "expected_committee_allowed": True, "expected_p5_allowed": True,
                                   "expected_candidate_count_min": 3, "expected_candidate_count_max": 10}])
    assert result["gate_passed"] is False


def test_all_receipts_dry_run_only():
    result = run_heldout_dry_run(_valid_fixture())
    for r in result["receipts"]:
        assert r.dry_run_only is True
        assert r.execution_attempted is False
        assert r.cloud_invoked is False
        assert r.local_model_invoked is False
        assert r.patch_apply_invoked is False
        assert r.solved is False
        assert r.claim_eligible is False
        assert r.public_claim_allowed is False
        assert r.production_ready is False
        assert r.runtime_behavior_changed is False
        assert r.verifier_required is True
        assert r.claim_gate_required is True


def test_json_serializable():
    result = run_heldout_dry_run(_valid_fixture())
    r = result["receipts"][0]
    d = {"case_id": r.case_id, "dry_run_only": r.dry_run_only}
    json_str = json.dumps(d)
    assert len(json_str) > 0
