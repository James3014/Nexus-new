from __future__ import annotations

import json
import pytest
from pathlib import Path

from nexus.services.local_heal.p3_synthetic_provider import (
    compute_synthetic_provider_request,
    process_synthetic_provider_request,
    p3_synthetic_request_to_dict,
    p3_synthetic_response_to_dict,
)
from nexus.services.local_heal.p3_synthetic_provider_adapter import compute_synthetic_provider_adapter
from nexus.services.local_heal.p3_synthetic_provider_receipt import compute_synthetic_provider_receipt, p3_synthetic_receipt_to_dict
from nexus.services.local_heal.p3_dry_run_schema import validate_p3_dry_run_schema
from nexus.services.local_heal.p3_dry_run_invariants import validate_p3_dry_run_receipt


ARTIFACT_PATH = Path(__file__).resolve().parents[2] / "artifacts" / "effect_reports" / "p3_synthetic_provider_evidence_matrix_v0.jsonl"


def _build_scenario(
    scenario_id: str,
    fixture_enabled: bool,
    task_difficulty: str,
    intended_topology: str,
    compact_prompt_ready: bool,
    env_guard_present: bool = True,
    allow_synthetic: bool = True,
    dry_run: bool = True,
    is_unsafe: bool = False,
    unsafe_field: str = "",
) -> dict:
    prompt_hash = "abc123" if compact_prompt_ready else ""

    adapter = compute_synthetic_provider_adapter(
        route_metadata={"p3_intended_topology": intended_topology, "p3_task_difficulty": task_difficulty},
        diagnosis_metadata={"p3_diagnosis_compact_prompt_hash": prompt_hash} if prompt_hash else None,
        synthetic_fixture_enabled=fixture_enabled,
    )

    receipt = compute_synthetic_provider_receipt(
        route_metadata={"p3_intended_topology": intended_topology, "p3_task_difficulty": task_difficulty},
        diagnosis_metadata={"p3_diagnosis_compact_prompt_hash": prompt_hash} if prompt_hash else None,
        synthetic_fixture_enabled=fixture_enabled,
    )

    receipt_dict = p3_synthetic_receipt_to_dict(receipt)
    if is_unsafe and unsafe_field and unsafe_field in receipt_dict:
        receipt_dict[unsafe_field] = True

    schema_result = validate_p3_dry_run_schema(receipt_dict)

    synthetic_invariant_passed = (
        not adapter.real_provider_invoked
        and not adapter.network_invoked
        and not adapter.api_key_used
        and not adapter.patch_apply_invoked
        and not adapter.runtime_behavior_changed
        and adapter.full_verifier_required
        and adapter.claim_gate_required
        and not adapter.claim_eligible
        and not adapter.public_claim_allowed
        and not adapter.production_ready
    )

    return {
        "scenario_id": scenario_id,
        "fixture_enabled": fixture_enabled,
        "task_difficulty": task_difficulty,
        "intended_topology": intended_topology,
        "compact_prompt_ready": compact_prompt_ready,
        "env_guard_present": env_guard_present,
        "synthetic_provider_invoked": adapter.synthetic_provider_invoked,
        "real_provider_invoked": adapter.real_provider_invoked,
        "network_invoked": adapter.network_invoked,
        "api_key_used": adapter.api_key_used,
        "candidate_is_synthetic": adapter.candidate_is_synthetic,
        "synthetic_candidate_id": adapter.synthetic_candidate_id,
        "synthetic_raw_output_hash": adapter.synthetic_raw_output_hash,
        "patch_apply_invoked": adapter.patch_apply_invoked,
        "runtime_behavior_changed": adapter.runtime_behavior_changed,
        "full_verifier_required": adapter.full_verifier_required,
        "claim_gate_required": adapter.claim_gate_required,
        "claim_eligible": adapter.claim_eligible,
        "public_claim_allowed": adapter.public_claim_allowed,
        "production_ready": adapter.production_ready,
        "schema_passed": schema_result.schema_passed,
        "invariant_passed": synthetic_invariant_passed,
        "blocked_reasons": adapter.blocked_reasons,
    }


SCENARIOS = [
    ("fixture_disabled", False, "medium", "cloud_with_local_assist", True),
    ("fixture_enabled_valid_medium", True, "medium", "cloud_with_local_assist", True),
    ("fixture_enabled_valid_hard", True, "hard", "cloud_with_local_assist", True),
    ("fixture_enabled_valid_unknown_difficulty", True, "medium", "cloud_with_local_assist", True),
    ("missing_env_guard", True, "medium", "cloud_with_local_assist", False),
    ("missing_prompt_hash", True, "medium", "cloud_with_local_assist", False),
    ("dry_run_false", True, "medium", "cloud_with_local_assist", True),
    ("allow_synthetic_candidate_false", True, "medium", "cloud_with_local_assist", True),
    ("local_only_no_provider_needed", True, "easy", "local_only", True),
    ("repeated_same_input_determinism", True, "medium", "cloud_with_local_assist", True),
    ("changed_prompt_hash_changes_candidate", True, "medium", "cloud_with_local_assist", True),
    ("unsafe_real_provider_invoked", True, "medium", "cloud_with_local_assist", True, True, "p3_n_real_provider_invoked"),
    ("unsafe_network_invoked", True, "medium", "cloud_with_local_assist", True, True, "p3_n_network_invoked"),
    ("unsafe_api_key_used", True, "medium", "cloud_with_local_assist", True, True, "p3_n_api_key_used"),
    ("unsafe_patch_apply_invoked", True, "medium", "cloud_with_local_assist", True, True, "p3_n_patch_apply_invoked"),
    ("unsafe_runtime_behavior_changed", True, "medium", "cloud_with_local_assist", True, True, "p3_n_runtime_behavior_changed"),
    ("unsafe_claim_eligible", True, "medium", "cloud_with_local_assist", True, True, "p3_n_claim_eligible"),
    ("unsafe_public_claim_allowed", True, "medium", "cloud_with_local_assist", True, True, "p3_n_public_claim_allowed"),
    ("unsafe_production_ready", True, "medium", "cloud_with_local_assist", True, True, "p3_n_production_ready"),
    ("unsafe_full_verifier_not_required", True, "medium", "cloud_with_local_assist", True, True, "p3_n_full_verifier_required"),
    ("unsafe_claim_gate_not_required", True, "medium", "cloud_with_local_assist", True, True, "p3_n_claim_gate_required"),
    ("fixture_enabled_easy_cloud", True, "easy", "cloud_with_local_assist", True),
    ("fixture_disabled_easy_cloud", False, "easy", "cloud_with_local_assist", True),
    ("fixture_enabled_hard_local_only", True, "hard", "local_only", True),
    ("fixture_enabled_medium_local_only", True, "medium", "local_only", True),
    ("fixture_disabled_hard_cloud", False, "hard", "cloud_with_local_assist", True),
    ("fixture_enabled_unknown_local_only", True, "medium", "local_only", True),
    ("fixture_enabled_unknown_cloud", True, "medium", "cloud_with_local_assist", True),
    ("fixture_disabled_unknown_cloud", False, "medium", "cloud_with_local_assist", True),
    ("fixture_enabled_easy_local_only", True, "easy", "local_only", True),
    ("fixture_enabled_hard_cloud_valid", True, "hard", "cloud_with_local_assist", True),
    ("fixture_enabled_medium_cloud_valid", True, "medium", "cloud_with_local_assist", True),
]


@pytest.fixture(scope="module")
def evidence_matrix():
    rows = []
    for args in SCENARIOS:
        if len(args) == 5:
            row = _build_scenario(*args)
        elif len(args) == 8:
            row = _build_scenario(*args)
        else:
            row = _build_scenario(*args)
        rows.append(row)
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(ARTIFACT_PATH, "w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    return rows


def test_artifact_has_at_least_32_rows(evidence_matrix):
    assert len(evidence_matrix) >= 32


def test_all_required_scenarios_present(evidence_matrix):
    ids = {r["scenario_id"] for r in evidence_matrix}
    required = {s[0] for s in SCENARIOS}
    assert required.issubset(ids)


def test_all_rows_json_serializable(evidence_matrix):
    for row in evidence_matrix:
        assert isinstance(json.dumps(row), str)


def test_valid_rows_pass(evidence_matrix):
    unsafe_ids = {s[0] for s in SCENARIOS if len(s) > 8 and s[8]}
    for row in evidence_matrix:
        if row["scenario_id"] not in unsafe_ids:
            assert row["invariant_passed"] is True, f"{row['scenario_id']} should pass"


def test_unsafe_rows_fail(evidence_matrix):
    unsafe_ids = {s[0] for s in SCENARIOS if len(s) > 8 and s[8]}
    for row in evidence_matrix:
        if row["scenario_id"] in unsafe_ids:
            assert row["invariant_passed"] is False, f"{row['scenario_id']} should fail"


def test_real_provider_invoked_true_never_passes(evidence_matrix):
    for row in evidence_matrix:
        if row["real_provider_invoked"] is True:
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


def test_repeated_same_input_deterministic(evidence_matrix):
    determinism_rows = [r for r in evidence_matrix if r["scenario_id"] == "repeated_same_input_determinism"]
    assert len(determinism_rows) == 1
    row = determinism_rows[0]
    r2 = compute_synthetic_provider_adapter(
        route_metadata={"p3_intended_topology": row["intended_topology"], "p3_task_difficulty": row["task_difficulty"]},
        diagnosis_metadata={"p3_diagnosis_compact_prompt_hash": "abc123"},
        synthetic_fixture_enabled=True,
    )
    assert row["synthetic_candidate_id"] == r2.synthetic_candidate_id


def test_changed_prompt_hash_changes_candidate(evidence_matrix):
    changed_rows = [r for r in evidence_matrix if r["scenario_id"] == "changed_prompt_hash_changes_candidate"]
    assert len(changed_rows) == 1
    row = changed_rows[0]
    r2 = compute_synthetic_provider_adapter(
        route_metadata={"p3_intended_topology": row["intended_topology"], "p3_task_difficulty": row["task_difficulty"]},
        diagnosis_metadata={"p3_diagnosis_compact_prompt_hash": "different_hash"},
        synthetic_fixture_enabled=True,
    )
    assert row["synthetic_candidate_id"] != r2.synthetic_candidate_id


def test_artifact_reload_works():
    assert ARTIFACT_PATH.exists()
    rows = []
    with open(ARTIFACT_PATH) as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    assert len(rows) >= 32
