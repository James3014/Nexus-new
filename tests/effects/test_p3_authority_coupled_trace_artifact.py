from __future__ import annotations

import json
import pytest
from pathlib import Path

from nexus.services.local_heal.p3_synthetic_e2e_trace import compute_synthetic_e2e_trace, p3_synthetic_e2e_trace_to_dict
from nexus.services.local_heal.p3_authority_coupling import compute_p3_authority_coupling, p3_authority_coupling_to_dict


ARTIFACT_PATH = Path(__file__).resolve().parents[2] / "artifacts" / "effect_reports" / "p3_authority_coupled_synthetic_trace_v0.jsonl"
O3_ARTIFACT_PATH = Path(__file__).resolve().parents[2] / "artifacts" / "effect_reports" / "p3_synthetic_e2e_trace_v0.jsonl"


SCENARIOS = [
    ("flag_off_shadow_only", False, "medium", "cloud_with_local_assist", True, True),
    ("local_only_easy", True, "easy", "local_only", True, True),
    ("cloud_medium_valid_synthetic", True, "medium", "cloud_with_local_assist", True, True),
    ("cloud_hard_valid_synthetic", True, "hard", "cloud_with_local_assist", True, True),
    ("missing_env_guard", False, "medium", "cloud_with_local_assist", True, True),
    ("missing_prompt_hash", True, "medium", "cloud_with_local_assist", False, True),
    ("synthetic_fixture_disabled", True, "medium", "cloud_with_local_assist", True, False),
    ("unsafe_real_provider_invoked", True, "medium", "cloud_with_local_assist", True, True, True, "p3_n_real_provider_invoked"),
    ("unsafe_network_invoked", True, "medium", "cloud_with_local_assist", True, True, True, "p3_n_network_invoked"),
    ("unsafe_public_claim_allowed", True, "medium", "cloud_with_local_assist", True, True, True, "p3_n_public_claim_allowed"),
    ("unsafe_production_ready", True, "medium", "cloud_with_local_assist", True, True, True, "p3_n_production_ready"),
]


def _build_row(args):
    if len(args) == 6:
        scenario_id, env, diff, topo, prompt, fixture = args
        trace = compute_synthetic_e2e_trace(
            scenario_id=scenario_id, env_flag_enabled=env, task_difficulty=diff,
            intended_topology=topo, compact_prompt_ready=prompt, synthetic_fixture_enabled=fixture,
        )
    else:
        scenario_id, env, diff, topo, prompt, fixture, is_unsafe, unsafe_field = args
        trace = compute_synthetic_e2e_trace(
            scenario_id=scenario_id, env_flag_enabled=env, task_difficulty=diff,
            intended_topology=topo, compact_prompt_ready=prompt, synthetic_fixture_enabled=fixture,
            is_unsafe=is_unsafe, unsafe_field=unsafe_field,
        )
    trace_dict = p3_synthetic_e2e_trace_to_dict(trace)
    coupling = compute_p3_authority_coupling(
        candidate_available=trace.canonical_candidate_available,
        candidate_is_synthetic=trace.candidate_is_synthetic,
    )
    coupling_dict = p3_authority_coupling_to_dict(coupling)
    return {**trace_dict, **coupling_dict}


@pytest.fixture(scope="module")
def evidence_matrix():
    rows = []
    for args in SCENARIOS:
        rows.append(_build_row(args))
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(ARTIFACT_PATH, "w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    return rows


def test_artifact_exists(evidence_matrix):
    assert len(evidence_matrix) >= 11


def test_artifact_reload_works():
    assert ARTIFACT_PATH.exists()
    rows = []
    with open(ARTIFACT_PATH) as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    assert len(rows) >= 11


def test_all_rows_require_p2_hash_truth(evidence_matrix):
    for row in evidence_matrix:
        assert row["p3_coupling_p2_hash_truth_required"] is True


def test_all_rows_require_p2_anchor_truth(evidence_matrix):
    for row in evidence_matrix:
        assert row["p3_coupling_p2_anchor_truth_required"] is True


def test_all_rows_require_p4_verifier(evidence_matrix):
    for row in evidence_matrix:
        assert row["p3_coupling_p4_full_verifier_required"] is True


def test_all_rows_require_p4_claim_gate(evidence_matrix):
    for row in evidence_matrix:
        assert row["p3_coupling_p4_claim_gate_required"] is True


def test_patch_apply_allowed_false_all_rows(evidence_matrix):
    for row in evidence_matrix:
        assert row["p3_coupling_patch_apply_allowed"] is False


def test_solved_allowed_false_all_rows(evidence_matrix):
    for row in evidence_matrix:
        assert row["p3_coupling_solved_allowed"] is False


def test_claim_eligible_allowed_false_all_rows(evidence_matrix):
    for row in evidence_matrix:
        assert row["p3_coupling_claim_eligible_allowed"] is False


def test_public_claim_allowed_false_all_rows(evidence_matrix):
    for row in evidence_matrix:
        assert row["p3_coupling_public_claim_allowed"] is False


def test_production_ready_false_all_rows(evidence_matrix):
    for row in evidence_matrix:
        assert row["p3_coupling_production_ready"] is False


def test_synthetic_candidate_rows_require_p2_apply(evidence_matrix):
    for row in evidence_matrix:
        if row.get("p3_trace_candidate_is_synthetic", False):
            assert row["p3_coupling_p2_apply_required"] is True
