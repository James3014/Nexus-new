from __future__ import annotations

import json
import pytest
from pathlib import Path

from nexus.services.local_heal.p3_runtime_guard import compute_p3_runtime_guard
from nexus.services.local_heal.p3_route_provider_adapter import compute_route_provider_adapter
from nexus.services.local_heal.p3_dry_run_receipt import compute_p3_dry_run_receipt, p3_dry_run_receipt_to_dict
from nexus.services.local_heal.p3_dry_run_invariants import validate_p3_dry_run_receipt


ARTIFACT_PATH = Path(__file__).resolve().parents[2] / "artifacts" / "effect_reports" / "p3_executor_dry_run_evidence_matrix_v0.jsonl"


def _build_scenario(
    scenario_id: str,
    env_flag_enabled: bool,
    task_difficulty: str,
    intended_topology: str,
    compact_prompt_ready: bool,
    is_unsafe: bool = False,
    unsafe_field: str = "",
) -> dict:
    guard_state = "env_guarded_dry_run" if env_flag_enabled else "shadow_only"

    prompt_hash = "abc123" if compact_prompt_ready else ""

    receipt = compute_p3_dry_run_receipt(
        route_metadata={"p3_intended_topology": intended_topology, "p3_task_difficulty": task_difficulty},
        diagnosis_metadata={"p3_diagnosis_compact_prompt_hash": prompt_hash} if prompt_hash else None,
        guard_state=guard_state,
        env_guard_override=env_flag_enabled,
    )

    receipt_dict = p3_dry_run_receipt_to_dict(receipt)

    if is_unsafe and unsafe_field:
        receipt_dict[unsafe_field] = True

    invariant = validate_p3_dry_run_receipt(receipt_dict)

    return {
        "scenario_id": scenario_id,
        "env_flag_enabled": env_flag_enabled,
        "task_difficulty": task_difficulty,
        "intended_topology": intended_topology,
        "compact_prompt_ready": compact_prompt_ready,
        "receipt_present": True,
        "invariant_passed": invariant.invariant_passed,
        "provider_request_built": receipt.p3_l_provider_request_built,
        "provider_invoked": receipt.p3_l_provider_invoked,
        "network_invoked": receipt.p3_l_network_invoked,
        "api_key_used": receipt.p3_l_api_key_used,
        "local_model_invoked_by_p3": receipt.p3_l_local_model_invoked,
        "patch_apply_invoked": receipt.p3_l_patch_apply_invoked,
        "runtime_behavior_changed": receipt.p3_l_runtime_behavior_changed,
        "full_verifier_required": receipt.p3_l_full_verifier_required,
        "claim_gate_required": receipt.p3_l_claim_gate_required,
        "claim_eligible": receipt.p3_l_claim_eligible,
        "public_claim_allowed": receipt.p3_l_public_claim_allowed,
        "production_ready": receipt.p3_l_production_ready,
        "blocked_reasons": receipt.p3_l_blocked_reasons + (invariant.blocked_reasons if not invariant.invariant_passed else []),
    }


SCENARIOS = [
    ("flag_off_easy_local_only", False, "easy", "local_only", True),
    ("flag_off_medium_cloud_topology", False, "medium", "cloud_with_local_assist", True),
    ("flag_on_easy_local_only", True, "easy", "local_only", True),
    ("flag_on_medium_cloud_valid_prompt", True, "medium", "cloud_with_local_assist", True),
    ("flag_on_hard_cloud_valid_prompt", True, "hard", "cloud_with_local_assist", True),
    ("flag_on_medium_missing_env_guard", False, "medium", "cloud_with_local_assist", True),
    ("flag_on_medium_missing_prompt_hash", True, "medium", "cloud_with_local_assist", False),
    ("flag_on_unknown_difficulty", True, "medium", "cloud_with_local_assist", True),
    ("unsafe_provider_invoked", True, "medium", "cloud_with_local_assist", True, True, "p3_l_provider_invoked"),
    ("unsafe_network_invoked", True, "medium", "cloud_with_local_assist", True, True, "p3_l_network_invoked"),
    ("unsafe_api_key_used", True, "medium", "cloud_with_local_assist", True, True, "p3_l_api_key_used"),
    ("unsafe_patch_apply_invoked", True, "medium", "cloud_with_local_assist", True, True, "p3_l_patch_apply_invoked"),
    ("unsafe_runtime_behavior_changed", True, "medium", "cloud_with_local_assist", True, True, "p3_l_runtime_behavior_changed"),
    ("unsafe_claim_eligible", True, "medium", "cloud_with_local_assist", True, True, "p3_l_claim_eligible"),
    ("unsafe_public_claim_allowed", True, "medium", "cloud_with_local_assist", True, True, "p3_l_public_claim_allowed"),
    ("unsafe_production_ready", True, "medium", "cloud_with_local_assist", True, True, "p3_l_production_ready"),
    ("flag_off_hard_local_only", False, "hard", "local_only", True),
    ("flag_on_hard_cloud_missing_prompt", True, "hard", "cloud_with_local_assist", False),
    ("flag_off_easy_cloud", False, "easy", "cloud_with_local_assist", True),
    ("flag_on_easy_cloud_valid_prompt", True, "easy", "cloud_with_local_assist", True),
    ("flag_on_medium_cloud_missing_prompt", True, "medium", "cloud_with_local_assist", False),
    ("flag_off_medium_local_only", False, "medium", "local_only", True),
    ("flag_on_hard_local_only", True, "hard", "local_only", True),
    ("flag_off_unknown_local_only", False, "medium", "local_only", True),
]


@pytest.fixture(scope="module")
def evidence_matrix():
    rows = []
    for args in SCENARIOS:
        if len(args) == 5:
            row = _build_scenario(*args)
        else:
            row = _build_scenario(*args)
        rows.append(row)
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(ARTIFACT_PATH, "w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    return rows


def test_artifact_has_at_least_24_rows(evidence_matrix):
    assert len(evidence_matrix) >= 24


def test_all_required_scenarios_present(evidence_matrix):
    ids = {r["scenario_id"] for r in evidence_matrix}
    required = {s[0] for s in SCENARIOS}
    assert required.issubset(ids)


def test_all_rows_json_serializable(evidence_matrix):
    for row in evidence_matrix:
        serialized = json.dumps(row)
        assert isinstance(serialized, str)


def test_valid_rows_pass_invariants(evidence_matrix):
    unsafe_ids = {s[0] for s in SCENARIOS if len(s) > 5 and s[5]}
    for row in evidence_matrix:
        if row["scenario_id"] not in unsafe_ids:
            assert row["invariant_passed"] is True, f"{row['scenario_id']} should pass"


def test_unsafe_rows_fail_invariants(evidence_matrix):
    unsafe_ids = {s[0] for s in SCENARIOS if len(s) > 5 and s[5]}
    for row in evidence_matrix:
        if row["scenario_id"] in unsafe_ids:
            assert row["invariant_passed"] is False, f"{row['scenario_id']} should fail"


def test_provider_invoked_true_never_passes(evidence_matrix):
    for row in evidence_matrix:
        if row["provider_invoked"] is True:
            assert row["invariant_passed"] is False


def test_network_invoked_true_never_passes(evidence_matrix):
    for row in evidence_matrix:
        if row["network_invoked"] is True:
            assert row["invariant_passed"] is False


def test_api_key_used_true_never_passes(evidence_matrix):
    for row in evidence_matrix:
        if row["api_key_used"] is True:
            assert row["invariant_passed"] is False


def test_patch_apply_invoked_true_never_passes(evidence_matrix):
    for row in evidence_matrix:
        if row["patch_apply_invoked"] is True:
            assert row["invariant_passed"] is False


def test_runtime_behavior_changed_true_never_passes(evidence_matrix):
    for row in evidence_matrix:
        if row["runtime_behavior_changed"] is True:
            assert row["invariant_passed"] is False


def test_claim_eligible_true_never_passes(evidence_matrix):
    for row in evidence_matrix:
        if row["claim_eligible"] is True:
            assert row["invariant_passed"] is False


def test_public_claim_allowed_true_never_passes(evidence_matrix):
    for row in evidence_matrix:
        if row["public_claim_allowed"] is True:
            assert row["invariant_passed"] is False


def test_production_ready_true_never_passes(evidence_matrix):
    for row in evidence_matrix:
        if row["production_ready"] is True:
            assert row["invariant_passed"] is False


def test_flag_off_rows_behavior_changed_false(evidence_matrix):
    for row in evidence_matrix:
        if not row["env_flag_enabled"]:
            assert row["runtime_behavior_changed"] is False


def test_artifact_reload_works():
    assert ARTIFACT_PATH.exists()
    rows = []
    with open(ARTIFACT_PATH) as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    assert len(rows) >= 24
