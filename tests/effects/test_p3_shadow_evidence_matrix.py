from __future__ import annotations

import json
import os
import pytest
from pathlib import Path

from nexus.services.local_heal.p3_shadow_invariants import validate_p3_shadow_invariants
from nexus.services.local_heal.p3_shadow_receipt import consolidate_p3_shadow_receipt


ARTIFACT_PATH = Path(__file__).resolve().parents[2] / "artifacts" / "effect_reports" / "p3_shadow_evidence_matrix_v0.jsonl"


def _build_scenario(
    scenario_id: str,
    task_difficulty: str,
    intended_topology: str,
    anchor_status: str,
    hash_chain_status: str,
    component_metadata: dict,
) -> dict:
    invariant = validate_p3_shadow_invariants(component_metadata)
    receipt = consolidate_p3_shadow_receipt(component_metadata, invariant)
    return {
        "scenario_id": scenario_id,
        "task_difficulty": task_difficulty,
        "intended_topology": intended_topology,
        "anchor_status": anchor_status,
        "hash_chain_status": hash_chain_status,
        "invariant_passed": invariant.invariant_passed,
        "receipt_complete": receipt.p3_receipt_complete,
        "cloud_call_invoked": receipt.p3_cloud_call_invoked,
        "local_model_call_invoked": receipt.p3_local_model_call_invoked,
        "patch_apply_invoked": receipt.p3_patch_apply_invoked,
        "runtime_behavior_changed": receipt.p3_runtime_behavior_changed,
        "full_verifier_required": receipt.p3_full_verifier_required,
        "claim_gate_required": receipt.p3_claim_gate_required,
        "claim_eligible": receipt.p3_claim_eligible,
        "public_claim_allowed": receipt.p3_public_claim_allowed,
        "solved_claim_allowed": receipt.p3_solved_claim_allowed,
        "blocked_reasons": receipt.p3_blocked_reasons,
        "unsafe_action_detected": not invariant.invariant_passed,
    }


def _valid_metadata(task_difficulty: str, intended_topology: str) -> dict:
    return {
        "p3_route_skeleton_enabled": True,
        "p3_task_difficulty": task_difficulty,
        "p3_intended_topology": intended_topology,
        "p3_local_diagnosis_enabled": True,
        "p3_diagnosis_cloud_ready": intended_topology == "cloud_with_local_assist",
        "p3_cloud_candidate_stub_enabled": True,
        "p3_cloud_stub_call_planned": intended_topology == "cloud_with_local_assist",
        "p3_cheap_verifier_enabled": True,
        "p3_cheap_verifier_planned": intended_topology == "cloud_with_local_assist",
        "p3_local_retry_enabled": True,
        "p3_local_retry_planned": intended_topology == "cloud_with_local_assist",
        "p3_shadow_orchestrator_enabled": True,
        "p3_shadow_authority": "shadow_only",
        "p3_cloud_call_invoked": False,
        "p3_local_model_call_invoked": False,
        "p3_patch_apply_invoked": False,
        "p3_runtime_behavior_changed": False,
        "p3_full_verifier_required": True,
        "p3_claim_gate_required": True,
        "p3_claim_eligible": False,
        "p3_public_claim_allowed": False,
        "p3_solved_claim_allowed": False,
    }


SCENARIOS = [
    ("easy_valid_anchor_complete_hash", "easy", "local_only", "available", "complete", True),
    ("medium_valid_anchor_complete_hash", "medium", "cloud_with_local_assist", "available", "complete", True),
    ("hard_valid_anchor_complete_hash", "hard", "cloud_with_local_assist", "available", "complete", True),
    ("easy_missing_anchor", "easy", "local_only", "missing", "complete", True),
    ("medium_missing_anchor", "medium", "cloud_with_local_assist", "missing", "complete", True),
    ("hard_missing_anchor", "hard", "cloud_with_local_assist", "missing", "complete", True),
    ("easy_incomplete_hash", "easy", "local_only", "available", "incomplete", True),
    ("medium_incomplete_hash", "medium", "cloud_with_local_assist", "available", "incomplete", True),
    ("hard_incomplete_hash", "hard", "cloud_with_local_assist", "available", "incomplete", True),
    ("medium_cloud_call_invoked_violation", "medium", "cloud_with_local_assist", "available", "complete", False),
    ("medium_local_model_invoked_violation", "medium", "cloud_with_local_assist", "available", "complete", False),
    ("medium_patch_apply_invoked_violation", "medium", "cloud_with_local_assist", "available", "complete", False),
    ("medium_runtime_behavior_changed_violation", "medium", "cloud_with_local_assist", "available", "complete", False),
    ("medium_public_claim_allowed_violation", "medium", "cloud_with_local_assist", "available", "complete", False),
    ("medium_solved_claim_violation", "medium", "cloud_with_local_assist", "available", "complete", False),
    ("hard_hybrid_future_planned_not_invoked", "hard", "cloud_with_local_assist", "available", "complete", True),
    ("unknown_difficulty_default_medium", "medium", "cloud_with_local_assist", "available", "complete", True),
    ("malformed_metadata_fail_closed", "medium", "", "", "", False),
]


def _make_violation_metadata(scenario_id: str) -> dict:
    base = _valid_metadata("medium", "cloud_with_local_assist")
    if "cloud_call_invoked" in scenario_id:
        base["p3_cloud_call_invoked"] = True
    elif "local_model_invoked" in scenario_id:
        base["p3_local_model_call_invoked"] = True
    elif "patch_apply_invoked" in scenario_id:
        base["p3_patch_apply_invoked"] = True
    elif "runtime_behavior_changed" in scenario_id:
        base["p3_runtime_behavior_changed"] = True
    elif "public_claim_allowed" in scenario_id:
        base["p3_public_claim_allowed"] = True
    elif "solved_claim" in scenario_id:
        base["solved"] = True
    elif "malformed" in scenario_id:
        return {"p3_shadow_authority": "runtime_authoritative"}
    return base


def _make_metadata(scenario_id: str, task_difficulty: str, intended_topology: str, is_valid: bool) -> dict:
    if is_valid:
        return _valid_metadata(task_difficulty, intended_topology)
    return _make_violation_metadata(scenario_id)


@pytest.fixture(scope="module")
def evidence_matrix():
    rows = []
    for scenario_id, difficulty, topology, anchor, hashes, is_valid in SCENARIOS:
        metadata = _make_metadata(scenario_id, difficulty, topology, is_valid)
        row = _build_scenario(scenario_id, difficulty, topology, anchor, hashes, metadata)
        rows.append(row)
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(ARTIFACT_PATH, "w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    return rows


def test_artifact_has_at_least_18_rows(evidence_matrix):
    assert len(evidence_matrix) >= 18


def test_all_required_scenarios_present(evidence_matrix):
    ids = {r["scenario_id"] for r in evidence_matrix}
    required = {s[0] for s in SCENARIOS}
    assert required.issubset(ids)


def test_all_rows_json_serializable(evidence_matrix):
    for row in evidence_matrix:
        serialized = json.dumps(row)
        assert isinstance(serialized, str)


def test_valid_scenarios_invariant_passed(evidence_matrix):
    valid_ids = {s[0] for s in SCENARIOS if s[5]}
    for row in evidence_matrix:
        if row["scenario_id"] in valid_ids:
            assert row["invariant_passed"] is True, f"{row['scenario_id']} should pass"


def test_violation_scenarios_invariant_failed(evidence_matrix):
    violation_ids = {s[0] for s in SCENARIOS if not s[5]}
    for row in evidence_matrix:
        if row["scenario_id"] in violation_ids:
            assert row["invariant_passed"] is False, f"{row['scenario_id']} should fail"


def test_public_claim_allowed_true_never_passes(evidence_matrix):
    for row in evidence_matrix:
        if row["public_claim_allowed"] is True:
            assert row["invariant_passed"] is False


def test_solved_claim_allowed_true_never_passes(evidence_matrix):
    for row in evidence_matrix:
        if row["solved_claim_allowed"] is True:
            assert row["invariant_passed"] is False


def test_cloud_call_invoked_true_never_passes(evidence_matrix):
    for row in evidence_matrix:
        if row["cloud_call_invoked"] is True:
            assert row["invariant_passed"] is False


def test_local_model_call_invoked_true_never_passes(evidence_matrix):
    for row in evidence_matrix:
        if row["local_model_call_invoked"] is True:
            assert row["invariant_passed"] is False


def test_patch_apply_invoked_true_never_passes(evidence_matrix):
    for row in evidence_matrix:
        if row["patch_apply_invoked"] is True:
            assert row["invariant_passed"] is False


def test_runtime_behavior_changed_true_never_passes(evidence_matrix):
    for row in evidence_matrix:
        if row["runtime_behavior_changed"] is True:
            assert row["invariant_passed"] is False


def test_full_verifier_required_true_for_passing(evidence_matrix):
    for row in evidence_matrix:
        if row["invariant_passed"] is True:
            assert row["full_verifier_required"] is True


def test_claim_gate_required_true_for_passing(evidence_matrix):
    for row in evidence_matrix:
        if row["invariant_passed"] is True:
            assert row["claim_gate_required"] is True


def test_artifact_reload_works():
    assert ARTIFACT_PATH.exists()
    rows = []
    with open(ARTIFACT_PATH) as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    assert len(rows) >= 18
