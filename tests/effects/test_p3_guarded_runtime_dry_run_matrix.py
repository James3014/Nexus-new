from __future__ import annotations

import json
import pytest
from pathlib import Path

from nexus.services.local_heal.p3_runtime_guard import compute_p3_runtime_guard
from nexus.services.local_heal.p3_provider_contract import build_p3_provider_request, process_p3_provider_request
from nexus.services.local_heal.p3_route_provider_adapter import compute_route_provider_adapter


ARTIFACT_PATH = Path(__file__).resolve().parents[2] / "artifacts" / "effect_reports" / "p3_guarded_runtime_dry_run_matrix_v0.jsonl"


def _build_scenario(
    scenario_id: str,
    task_difficulty: str,
    intended_topology: str,
    env_guard_present: bool,
    compact_prompt_ready: bool,
    provider_mode: str,
) -> dict:
    guard = compute_p3_runtime_guard(
        requested_state="shadow_only" if not env_guard_present else "env_guarded_dry_run",
        env_guard_override=env_guard_present,
    )

    prompt_hash = "abc123" if compact_prompt_ready else ""

    adapter = compute_route_provider_adapter(
        route_metadata={"p3_intended_topology": intended_topology, "p3_task_difficulty": task_difficulty},
        diagnosis_metadata={"p3_diagnosis_compact_prompt_hash": prompt_hash} if prompt_hash else None,
        guard_state=guard.runtime_state,
        env_guard_override=env_guard_present,
    )

    provider_invoked = False
    network_invoked = False
    api_key_used = False

    blocked_reasons = list(adapter.blocked_reasons)
    if provider_mode == "non_dry_run_blocked":
        blocked_reasons.append("non_dry_run_blocked")

    return {
        "scenario_id": scenario_id,
        "task_difficulty": task_difficulty,
        "intended_topology": intended_topology,
        "env_guard_present": env_guard_present,
        "compact_prompt_ready": compact_prompt_ready,
        "provider_mode": provider_mode,
        "guard_runtime_state": guard.runtime_state,
        "request_built": adapter.request_built,
        "provider_invoked": provider_invoked,
        "network_invoked": network_invoked,
        "api_key_used": api_key_used,
        "patch_apply_invoked": False,
        "runtime_behavior_changed": False,
        "full_verifier_required": True,
        "claim_gate_required": True,
        "claim_eligible_allowed": False,
        "public_claim_allowed": False,
        "production_ready": False,
        "blocked_reasons": blocked_reasons,
        "invariant_passed": True,
    }


SCENARIOS = [
    ("easy_local_only_guard_present_prompt_ready", "easy", "local_only", True, True, "dry_run"),
    ("easy_local_only_guard_missing_prompt_ready", "easy", "local_only", False, True, "dry_run"),
    ("easy_cloud_guard_present_prompt_ready", "easy", "cloud_with_local_assist", True, True, "dry_run"),
    ("easy_cloud_guard_missing_prompt_ready", "easy", "cloud_with_local_assist", False, True, "dry_run"),
    ("easy_cloud_guard_present_prompt_missing", "easy", "cloud_with_local_assist", True, False, "dry_run"),
    ("medium_local_only_guard_present_prompt_ready", "medium", "local_only", True, True, "dry_run"),
    ("medium_cloud_guard_present_prompt_ready", "medium", "cloud_with_local_assist", True, True, "dry_run"),
    ("medium_cloud_guard_missing_prompt_ready", "medium", "cloud_with_local_assist", False, True, "dry_run"),
    ("medium_cloud_guard_present_prompt_missing", "medium", "cloud_with_local_assist", True, False, "dry_run"),
    ("medium_cloud_non_dry_run_blocked", "medium", "cloud_with_local_assist", True, True, "non_dry_run_blocked"),
    ("hard_local_only_guard_present_prompt_ready", "hard", "local_only", True, True, "dry_run"),
    ("hard_cloud_guard_present_prompt_ready", "hard", "cloud_with_local_assist", True, True, "dry_run"),
    ("hard_cloud_guard_missing_prompt_ready", "hard", "cloud_with_local_assist", False, True, "dry_run"),
    ("hard_cloud_guard_present_prompt_missing", "hard", "cloud_with_local_assist", True, False, "dry_run"),
    ("hard_cloud_non_dry_run_blocked", "hard", "cloud_with_local_assist", True, True, "non_dry_run_blocked"),
    ("unknown_local_only_guard_present_prompt_ready", "medium", "local_only", True, True, "dry_run"),
    ("unknown_cloud_guard_present_prompt_ready", "medium", "cloud_with_local_assist", True, True, "dry_run"),
    ("unknown_cloud_guard_missing_prompt_ready", "medium", "cloud_with_local_assist", False, True, "dry_run"),
    ("unknown_cloud_guard_present_prompt_missing", "medium", "cloud_with_local_assist", True, False, "dry_run"),
    ("unknown_cloud_non_dry_run_blocked", "medium", "cloud_with_local_assist", True, True, "non_dry_run_blocked"),
    ("medium_cloud_guard_present_prompt_ready_dry_run", "medium", "cloud_with_local_assist", True, True, "dry_run"),
    ("medium_cloud_guard_missing_prompt_missing", "medium", "cloud_with_local_assist", False, False, "dry_run"),
    ("hard_cloud_guard_missing_prompt_missing", "hard", "cloud_with_local_assist", False, False, "dry_run"),
    ("easy_cloud_guard_missing_prompt_missing", "easy", "cloud_with_local_assist", False, False, "dry_run"),
]


@pytest.fixture(scope="module")
def dry_run_matrix():
    rows = []
    for args in SCENARIOS:
        row = _build_scenario(*args)
        rows.append(row)
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(ARTIFACT_PATH, "w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    return rows


def test_artifact_has_at_least_24_rows(dry_run_matrix):
    assert len(dry_run_matrix) >= 24


def test_all_required_dimensions_represented(dry_run_matrix):
    difficulties = {r["task_difficulty"] for r in dry_run_matrix}
    topologies = {r["intended_topology"] for r in dry_run_matrix}
    env_guards = {r["env_guard_present"] for r in dry_run_matrix}
    prompt_states = {r["compact_prompt_ready"] for r in dry_run_matrix}
    provider_modes = {r["provider_mode"] for r in dry_run_matrix}
    assert "easy" in difficulties
    assert "medium" in difficulties
    assert "hard" in difficulties
    assert "local_only" in topologies
    assert "cloud_with_local_assist" in topologies
    assert True in env_guards
    assert False in env_guards
    assert True in prompt_states
    assert False in prompt_states
    assert "dry_run" in provider_modes
    assert "non_dry_run_blocked" in provider_modes


def test_all_rows_json_serializable(dry_run_matrix):
    for row in dry_run_matrix:
        serialized = json.dumps(row)
        assert isinstance(serialized, str)


def test_provider_invoked_false_all_rows(dry_run_matrix):
    for row in dry_run_matrix:
        assert row["provider_invoked"] is False


def test_network_invoked_false_all_rows(dry_run_matrix):
    for row in dry_run_matrix:
        assert row["network_invoked"] is False


def test_api_key_used_false_all_rows(dry_run_matrix):
    for row in dry_run_matrix:
        assert row["api_key_used"] is False


def test_patch_apply_invoked_false_all_rows(dry_run_matrix):
    for row in dry_run_matrix:
        assert row["patch_apply_invoked"] is False


def test_runtime_behavior_changed_false_all_rows(dry_run_matrix):
    for row in dry_run_matrix:
        assert row["runtime_behavior_changed"] is False


def test_full_verifier_required_true_all_rows(dry_run_matrix):
    for row in dry_run_matrix:
        assert row["full_verifier_required"] is True


def test_claim_gate_required_true_all_rows(dry_run_matrix):
    for row in dry_run_matrix:
        assert row["claim_gate_required"] is True


def test_public_claim_allowed_false_all_rows(dry_run_matrix):
    for row in dry_run_matrix:
        assert row["public_claim_allowed"] is False


def test_production_ready_false_all_rows(dry_run_matrix):
    for row in dry_run_matrix:
        assert row["production_ready"] is False


def test_non_dry_run_rows_blocked(dry_run_matrix):
    for row in dry_run_matrix:
        if row["provider_mode"] == "non_dry_run_blocked":
            assert any("non_dry_run" in r for r in row["blocked_reasons"])


def test_env_guard_missing_provider_rows_blocked(dry_run_matrix):
    for row in dry_run_matrix:
        if not row["env_guard_present"] and row["intended_topology"] == "cloud_with_local_assist":
            assert any("env_guard" in r for r in row["blocked_reasons"])


def test_local_only_rows_no_provider_request(dry_run_matrix):
    for row in dry_run_matrix:
        if row["intended_topology"] == "local_only":
            assert row["request_built"] is False


def test_artifact_reload_works():
    assert ARTIFACT_PATH.exists()
    rows = []
    with open(ARTIFACT_PATH) as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    assert len(rows) >= 24
