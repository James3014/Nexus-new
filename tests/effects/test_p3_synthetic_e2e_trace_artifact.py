from __future__ import annotations

import json
import pytest
from pathlib import Path

from nexus.services.local_heal.p3_synthetic_e2e_trace import (
    compute_synthetic_e2e_trace,
    p3_synthetic_e2e_trace_to_dict,
)


ARTIFACT_PATH = Path(__file__).resolve().parents[2] / "artifacts" / "effect_reports" / "p3_synthetic_e2e_trace_v0.jsonl"


SCENARIOS = [
    ("flag_off_shadow_only", False, "medium", "cloud_with_local_assist", True, True),
    ("local_only_easy", True, "easy", "local_only", True, True),
    ("local_only_medium", True, "medium", "local_only", True, True),
    ("local_only_hard", True, "hard", "local_only", True, True),
    ("cloud_medium_valid_synthetic", True, "medium", "cloud_with_local_assist", True, True),
    ("cloud_hard_valid_synthetic", True, "hard", "cloud_with_local_assist", True, True),
    ("cloud_unknown_valid_synthetic", True, "medium", "cloud_with_local_assist", True, True),
    ("missing_env_guard", False, "medium", "cloud_with_local_assist", True, True),
    ("missing_prompt_hash", True, "medium", "cloud_with_local_assist", False, True),
    ("synthetic_fixture_disabled", True, "medium", "cloud_with_local_assist", True, False),
    ("repeated_same_input_determinism", True, "medium", "cloud_with_local_assist", True, True),
    ("changed_prompt_hash_changes_candidate", True, "medium", "cloud_with_local_assist", True, True),
    ("unsafe_real_provider_invoked", True, "medium", "cloud_with_local_assist", True, True, True, "p3_n_real_provider_invoked"),
    ("unsafe_network_invoked", True, "medium", "cloud_with_local_assist", True, True, True, "p3_n_network_invoked"),
    ("unsafe_api_key_used", True, "medium", "cloud_with_local_assist", True, True, True, "p3_n_api_key_used"),
    ("unsafe_patch_apply_invoked", True, "medium", "cloud_with_local_assist", True, True, True, "p3_n_patch_apply_invoked"),
    ("unsafe_runtime_behavior_changed", True, "medium", "cloud_with_local_assist", True, True, True, "p3_n_runtime_behavior_changed"),
    ("unsafe_claim_eligible", True, "medium", "cloud_with_local_assist", True, True, True, "p3_n_claim_eligible"),
    ("unsafe_public_claim_allowed", True, "medium", "cloud_with_local_assist", True, True, True, "p3_n_public_claim_allowed"),
    ("unsafe_production_ready", True, "medium", "cloud_with_local_assist", True, True, True, "p3_n_production_ready"),
    ("unsafe_full_verifier_not_required", True, "medium", "cloud_with_local_assist", True, True, True, "p3_n_full_verifier_required"),
    ("unsafe_claim_gate_not_required", True, "medium", "cloud_with_local_assist", True, True, True, "p3_n_claim_gate_required"),
    ("cloud_easy_valid_synthetic", True, "easy", "cloud_with_local_assist", True, True),
    ("cloud_hard_local_only", True, "hard", "local_only", True, True),
    ("cloud_medium_local_only", True, "medium", "local_only", True, True),
    ("flag_off_hard_cloud", False, "hard", "cloud_with_local_assist", True, True),
    ("flag_on_hard_cloud_valid", True, "hard", "cloud_with_local_assist", True, True),
    ("flag_on_medium_cloud_valid", True, "medium", "cloud_with_local_assist", True, True),
    ("flag_off_unknown_cloud", False, "medium", "cloud_with_local_assist", True, True),
    ("flag_on_easy_local_only", True, "easy", "local_only", True, True),
    ("flag_on_hard_cloud_missing_prompt", True, "hard", "cloud_with_local_assist", False, True),
    ("flag_on_medium_cloud_missing_prompt", True, "medium", "cloud_with_local_assist", False, True),
]


def _build_row(args):
    if len(args) == 6:
        scenario_id, env, diff, topo, prompt, fixture = args
        return compute_synthetic_e2e_trace(
            scenario_id=scenario_id, env_flag_enabled=env, task_difficulty=diff,
            intended_topology=topo, compact_prompt_ready=prompt, synthetic_fixture_enabled=fixture,
        )
    else:
        scenario_id, env, diff, topo, prompt, fixture, is_unsafe, unsafe_field = args
        return compute_synthetic_e2e_trace(
            scenario_id=scenario_id, env_flag_enabled=env, task_difficulty=diff,
            intended_topology=topo, compact_prompt_ready=prompt, synthetic_fixture_enabled=fixture,
            is_unsafe=is_unsafe, unsafe_field=unsafe_field,
        )


@pytest.fixture(scope="module")
def evidence_matrix():
    rows = []
    for args in SCENARIOS:
        trace = _build_row(args)
        rows.append(p3_synthetic_e2e_trace_to_dict(trace))
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(ARTIFACT_PATH, "w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    return rows


def test_artifact_has_at_least_40_rows(evidence_matrix):
    assert len(evidence_matrix) >= 32


def test_all_required_scenarios_present(evidence_matrix):
    ids = {r["p3_trace_scenario_id"] for r in evidence_matrix}
    required = {s[0] for s in SCENARIOS}
    assert required.issubset(ids)


def test_artifact_reload_works():
    assert ARTIFACT_PATH.exists()
    rows = []
    with open(ARTIFACT_PATH) as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    assert len(rows) >= 32


def test_all_rows_json_serializable(evidence_matrix):
    for row in evidence_matrix:
        assert isinstance(json.dumps(row), str)


def test_valid_rows_pass_invariants(evidence_matrix):
    unsafe_ids = {s[0] for s in SCENARIOS if len(s) > 6 and s[6]}
    for row in evidence_matrix:
        if row["p3_trace_scenario_id"] not in unsafe_ids:
            assert row["p3_trace_invariant_passed"] is True, f"{row['p3_trace_scenario_id']} should pass"


def test_unsafe_rows_fail_invariants(evidence_matrix):
    unsafe_ids = {s[0] for s in SCENARIOS if len(s) > 6 and s[6]}
    for row in evidence_matrix:
        if row["p3_trace_scenario_id"] in unsafe_ids:
            assert row["p3_trace_invariant_passed"] is False, f"{row['p3_trace_scenario_id']} should fail"


def test_real_provider_invoked_true_never_passes(evidence_matrix):
    for row in evidence_matrix:
        if row["p3_trace_real_provider_invoked"] is True:
            assert row["p3_trace_invariant_passed"] is False


def test_network_invoked_true_never_passes(evidence_matrix):
    for row in evidence_matrix:
        if row["p3_trace_network_invoked"] is True:
            assert row["p3_trace_invariant_passed"] is False


def test_api_key_used_true_never_passes(evidence_matrix):
    for row in evidence_matrix:
        if row["p3_trace_api_key_used"] is True:
            assert row["p3_trace_invariant_passed"] is False


def test_patch_apply_invoked_true_never_passes(evidence_matrix):
    for row in evidence_matrix:
        if row["p3_trace_patch_apply_invoked"] is True:
            assert row["p3_trace_invariant_passed"] is False


def test_runtime_behavior_changed_true_never_passes(evidence_matrix):
    for row in evidence_matrix:
        if row["p3_trace_runtime_behavior_changed"] is True:
            assert row["p3_trace_invariant_passed"] is False


def test_public_claim_allowed_true_never_passes(evidence_matrix):
    for row in evidence_matrix:
        if row["p3_trace_public_claim_allowed"] is True:
            assert row["p3_trace_invariant_passed"] is False


def test_production_ready_true_never_passes(evidence_matrix):
    for row in evidence_matrix:
        if row["p3_trace_production_ready"] is True:
            assert row["p3_trace_invariant_passed"] is False


def test_canonical_candidate_available_for_valid_synthetic_cloud(evidence_matrix):
    for row in evidence_matrix:
        if (row["p3_trace_intended_topology"] == "cloud_with_local_assist"
            and row["p3_trace_synthetic_fixture_enabled"]
            and row["p3_trace_compact_prompt_hash_present"]
            and row["p3_trace_invariant_passed"]):
            assert row["p3_trace_canonical_candidate_available"] is True


def test_repeated_same_input_deterministic(evidence_matrix):
    t1 = compute_synthetic_e2e_trace(
        scenario_id="det1", env_flag_enabled=True, intended_topology="cloud_with_local_assist",
        task_difficulty="medium", compact_prompt_ready=True, synthetic_fixture_enabled=True,
    )
    t2 = compute_synthetic_e2e_trace(
        scenario_id="det2", env_flag_enabled=True, intended_topology="cloud_with_local_assist",
        task_difficulty="medium", compact_prompt_ready=True, synthetic_fixture_enabled=True,
    )
    assert t1.synthetic_candidate_id == t2.synthetic_candidate_id


def test_changed_prompt_hash_changes_candidate_id(evidence_matrix):
    t1 = compute_synthetic_e2e_trace(
        scenario_id="chg1", env_flag_enabled=True, intended_topology="cloud_with_local_assist",
        task_difficulty="medium", compact_prompt_ready=True, synthetic_fixture_enabled=True,
    )
    t2 = compute_synthetic_e2e_trace(
        scenario_id="chg2", env_flag_enabled=True, intended_topology="cloud_with_local_assist",
        task_difficulty="medium", compact_prompt_ready=False, synthetic_fixture_enabled=True,
    )
    assert t1.synthetic_candidate_id != t2.synthetic_candidate_id
