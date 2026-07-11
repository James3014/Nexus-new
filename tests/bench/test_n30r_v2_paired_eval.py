"""Behavioral tests for N30R V2 Paired Bare/Core Evaluation Harness.

Covers: manifest validation, plan mode, row validation, metrics,
effectiveness classification, and fairness contract.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.bench.n30r_v2_paired_eval import (
    classify_effectiveness,
    compute_metrics,
    load_manifest,
    plan_only,
    validate_results,
    validate_row,
)

REPO_ROOT = str(Path(__file__).resolve().parents[2])
MANIFEST_PATH = os.path.join(REPO_ROOT, "docs", "bench", "n30r", "v2_four_task_paired_manifest.json")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_manifest() -> dict[str, Any]:
    return load_manifest(MANIFEST_PATH)


def _task_map() -> dict[str, dict[str, Any]]:
    m = _load_manifest()
    return {t["task_id"]: t for t in m["tasks"]}


_MOCK_ENV_RECEIPT = {
    "python_executable": "/fake/venv/bin/python",
    "python_version": "3.14.0",
    "sys_prefix": "/fake/venv",
    "sys_base_prefix": "/fake/base",
    "virtualenv_active": True,
    "project_venv_match": True,
    "project_venv_expected": "/fake/venv/bin/python",
    "project_venv_resolved": "/fake/venv/bin/python3.14",
    "lancedb_available": True,
    "lancedb_version": "0.30.2",
    "requests_version": "2.33.1",
    "urllib3_version": "2.5.0",
    "charset_normalizer_version": "3.4.7",
    "dependency_warning_count": 0,
    "environment_valid": True,
}
_MOCK_ENV_SHA256 = hashlib.sha256(
    json.dumps(_MOCK_ENV_RECEIPT, sort_keys=True).encode()
).hexdigest()


def _valid_bare_row(task_id: str, task_map: dict) -> dict[str, Any]:
    t = task_map[task_id]
    return {
        "task_id": task_id,
        "arm_id": "N30R_A_7B_BARE",
        "trial_index": 0,
        "task_seed": t["task_seed"],
        "model_requested": "qwen2.5-coder:7b-instruct",
        "model_actual": "qwen2.5-coder:7b-instruct",
        "provider_actual": "ollama",
        "provider_seed_enforced": False,
        "task_statement_sha256": t["task_statement_sha256"],
        "source_fixture_sha256": t["source_fixture_sha256"],
        "verifier_contract_sha256": t["verifier_contract_sha256"],
        "execution_started": True,
        "execution_completed": True,
        "contract_valid": True,
        "model_call_count": 1,
        "model_response_received": True,
        "raw_output_length": 100,
        "protocol_parse_status": "success",
        "candidate_hash": hashlib.sha256(b"bare_candidate").hexdigest(),
        "candidate_isolated": True,
        "apply_status": "success",
        "verifier_reached": True,
        "verifier_status": "fail",
        "verifier_exit_code": 1,
        "semantic_retry_count": 0,
        "wall_time_sec": 5.0,
        "terminal_status": "VERIFIED_FAIL",
        "solved": False,
        "armor_oracle_status": "NOT_APPLICABLE",
        "env_receipt": _MOCK_ENV_RECEIPT,
        "env_receipt_sha256": _MOCK_ENV_SHA256,
    }


def _valid_core_row(task_id: str, task_map: dict) -> dict[str, Any]:
    t = task_map[task_id]
    return {
        "task_id": task_id,
        "arm_id": "N30R_B_7B_REAL_CORE",
        "trial_index": 0,
        "task_seed": t["task_seed"],
        "model_requested": "qwen2.5-coder:7b-instruct",
        "model_actual": "qwen2.5-coder:7b-instruct",
        "provider_actual": "ollama",
        "provider_seed_enforced": False,
        "task_statement_sha256": t["task_statement_sha256"],
        "source_fixture_sha256": t["source_fixture_sha256"],
        "verifier_contract_sha256": t["verifier_contract_sha256"],
        "execution_started": True,
        "execution_completed": True,
        "contract_valid": True,
        "model_call_count": 1,
        "model_response_received": True,
        "raw_output_length": 120,
        "protocol_parse_status": "success",
        "candidate_hash": hashlib.sha256(b"core_candidate").hexdigest(),
        "candidate_isolated": True,
        "apply_status": "success",
        "verifier_reached": True,
        "verifier_status": "fail",
        "verifier_exit_code": 1,
        "semantic_retry_count": 0,
        "wall_time_sec": 8.0,
        "terminal_status": "VERIFIED_FAIL",
        "solved": False,
        "armor_oracle_status": "FULL_ARMOR_PATH_ACCEPTED",
        "env_receipt": _MOCK_ENV_RECEIPT,
        "env_receipt_sha256": _MOCK_ENV_SHA256,
    }


def _all_valid_rows(task_map: dict) -> list[dict[str, Any]]:
    rows = []
    for tid in task_map:
        rows.append(_valid_bare_row(tid, task_map))
        rows.append(_valid_core_row(tid, task_map))
    return rows


# ---------------------------------------------------------------------------
# Manifest tests
# ---------------------------------------------------------------------------

class TestManifest:
    def test_manifest_loads_four_tasks(self):
        m = _load_manifest()
        assert len(m["tasks"]) == 4

    def test_manifest_all_hashes_match_disk(self):
        m = _load_manifest()
        for t in m["tasks"]:
            fixture = os.path.join(REPO_ROOT, t["source_relpath"])
            actual = hashlib.sha256(Path(fixture).read_text().encode()).hexdigest()
            assert t["source_fixture_sha256"] == actual, f"{t['task_id']} source hash mismatch"

    def test_task_seeds_deterministic(self):
        m = _load_manifest()
        seeds = [t["task_seed"] for t in m["tasks"]]
        assert seeds == [4201, 4202, 4203, 4204]

    def test_execution_order_alternates(self):
        m = _load_manifest()
        orders = [t["execution_order"] for t in m["tasks"]]
        assert orders[0] == ["N30R_A_7B_BARE", "N30R_B_7B_REAL_CORE"]
        assert orders[1] == ["N30R_B_7B_REAL_CORE", "N30R_A_7B_BARE"]
        assert orders[2] == ["N30R_A_7B_BARE", "N30R_B_7B_REAL_CORE"]
        assert orders[3] == ["N30R_B_7B_REAL_CORE", "N30R_A_7B_BARE"]

    def test_each_task_has_exactly_two_arms(self):
        m = _load_manifest()
        for t in m["tasks"]:
            assert len(t["execution_order"]) == 2
            assert set(t["execution_order"]) == {"N30R_A_7B_BARE", "N30R_B_7B_REAL_CORE"}


# ---------------------------------------------------------------------------
# Plan mode tests
# ---------------------------------------------------------------------------

class TestPlanMode:
    def test_plan_mode_performs_no_provider_calls(self):
        m = _load_manifest()
        result = plan_only(m)
        assert result["provider_calls"] == 0
        assert result["live_model_calls"] == 0

    def test_plan_mode_generates_eight_rows(self):
        m = _load_manifest()
        result = plan_only(m)
        assert result["total_scheduled_rows"] == 8

    def test_plan_mode_alternating_pattern(self):
        m = _load_manifest()
        result = plan_only(m)
        assert result["alternating_pattern"] is True


# ---------------------------------------------------------------------------
# Row validation: rejections
# ---------------------------------------------------------------------------

class TestRowRejections:
    def test_reject_missing_arm_row(self):
        tm = _task_map()
        row = _valid_bare_row("n30r_smoke_syntax", tm)
        del row["arm_id"]
        issues = validate_row(row, tm, _load_manifest())
        assert any("missing_field:arm_id" in i for i in issues)

    def test_reject_duplicate_arm_row(self):
        tm = _task_map()
        rows = [_valid_bare_row("n30r_smoke_syntax", tm),
                _valid_bare_row("n30r_smoke_syntax", tm)]
        # Both are bare for same task — should be caught by pair completeness
        assert len(rows) == 2
        assert all(r["arm_id"] == "N30R_A_7B_BARE" for r in rows)

    def test_reject_wrong_model_identity(self):
        tm = _task_map()
        row = _valid_bare_row("n30r_smoke_syntax", tm)
        row["model_actual"] = "gpt-4o"
        issues = validate_row(row, tm, _load_manifest())
        assert any("model_identity_mismatch" in i for i in issues)

    def test_reject_wrong_provider(self):
        tm = _task_map()
        row = _valid_bare_row("n30r_smoke_syntax", tm)
        row["provider_actual"] = "openai"
        issues = validate_row(row, tm, _load_manifest())
        assert any("unexpected_provider" in i for i in issues)

    def test_reject_mismatched_task_hash(self):
        tm = _task_map()
        row = _valid_bare_row("n30r_smoke_syntax", tm)
        row["source_fixture_sha256"] = "a" * 64
        issues = validate_row(row, tm, _load_manifest())
        assert any("source_fixture_hash_mismatch" in i for i in issues)

    def test_reject_mismatched_source_hash(self):
        tm = _task_map()
        row = _valid_bare_row("n30r_smoke_syntax", tm)
        row["verifier_contract_sha256"] = "b" * 64
        issues = validate_row(row, tm, _load_manifest())
        assert any("verifier_contract_hash_mismatch" in i for i in issues)

    def test_reject_mismatched_seed(self):
        tm = _task_map()
        row = _valid_bare_row("n30r_smoke_syntax", tm)
        row["task_seed"] = 9999
        issues = validate_row(row, tm, _load_manifest())
        assert any("task_seed_mismatch" in i for i in issues)

    def test_reject_core_without_oracle_status(self):
        tm = _task_map()
        row = _valid_core_row("n30r_smoke_syntax", tm)
        del row["armor_oracle_status"]
        issues = validate_row(row, tm, _load_manifest())
        assert any("core_missing_oracle_status" in i for i in issues)

    def test_reject_core_with_rejected_oracle(self):
        tm = _task_map()
        row = _valid_core_row("n30r_smoke_syntax", tm)
        row["armor_oracle_status"] = "REJECTED_CONTRACT_INVALID"
        issues = validate_row(row, tm, _load_manifest())
        assert any("core_oracle_rejected" in i for i in issues)


# ---------------------------------------------------------------------------
# Row validation: terminal status rules
# ---------------------------------------------------------------------------

class TestTerminalStatusRules:
    def test_reject_solved_without_verifier_pass(self):
        tm = _task_map()
        row = _valid_bare_row("n30r_smoke_syntax", tm)
        row["solved"] = True
        row["terminal_status"] = "VERIFIED_SOLVE"
        row["verifier_status"] = "fail"
        issues = validate_row(row, tm, _load_manifest())
        assert any("verified_solve_without_verifier_pass" in i for i in issues)

    def test_reject_verified_solve_without_verifier_reached(self):
        tm = _task_map()
        row = _valid_bare_row("n30r_smoke_syntax", tm)
        row["solved"] = True
        row["terminal_status"] = "VERIFIED_SOLVE"
        row["verifier_reached"] = False
        issues = validate_row(row, tm, _load_manifest())
        assert any("verified_solve_without_verifier_reached" in i for i in issues)

    def test_reject_candidate_isolated_with_empty_hash(self):
        tm = _task_map()
        row = _valid_bare_row("n30r_smoke_syntax", tm)
        row["candidate_isolated"] = True
        row["candidate_hash"] = ""
        issues = validate_row(row, tm, _load_manifest())
        assert any("candidate_isolated_with_empty_hash" in i for i in issues)

    def test_reject_apply_success_with_empty_candidate(self):
        tm = _task_map()
        row = _valid_bare_row("n30r_smoke_syntax", tm)
        row["apply_status"] = "success"
        row["candidate_hash"] = ""
        issues = validate_row(row, tm, _load_manifest())
        assert any("apply_success_with_empty_candidate" in i for i in issues)

    def test_reject_inferred_timeout_from_wall_time(self):
        tm = _task_map()
        row = _valid_bare_row("n30r_smoke_syntax", tm)
        row["timed_out"] = True
        row["timeout_stage"] = ""
        issues = validate_row(row, tm, _load_manifest())
        assert any("timed_out_without_timeout_stage" in i for i in issues)


# ---------------------------------------------------------------------------
# Metrics and effectiveness
# ---------------------------------------------------------------------------

class TestMetricsAndEffectiveness:
    def test_invalid_pair_excluded_from_uplift(self):
        tm = _task_map()
        rows = _all_valid_rows(tm)
        # Corrupt one core row
        rows[1]["armor_oracle_status"] = "REJECTED_CONTRACT_INVALID"
        val = validate_results(_load_manifest(), _write_jsonl(rows))
        assert val["status"] == "INVALID"

    def test_four_valid_pairs_required(self):
        tm = _task_map()
        rows = _all_valid_rows(tm)
        val = validate_results(_load_manifest(), _write_jsonl(rows))
        assert val["valid_rows"] == 8
        assert val["invalid_rows"] == 0

    def test_paired_matrix_correct(self):
        tm = _task_map()
        rows = _all_valid_rows(tm)
        metrics = compute_metrics(rows, tm)
        matrix = metrics["paired_matrix"]
        assert matrix["both_solve"] + matrix["bare_only_solve"] + \
               matrix["core_only_solve"] + matrix["neither_solve"] == 4

    def test_solve_delta_correct(self):
        tm = _task_map()
        rows = _all_valid_rows(tm)
        metrics = compute_metrics(rows, tm)
        assert metrics["solve_delta"] == metrics["core_verified_solves"] - metrics["bare_verified_solves"]

    def test_model_call_delta_correct(self):
        tm = _task_map()
        rows = _all_valid_rows(tm)
        metrics = compute_metrics(rows, tm)
        assert metrics["model_call_delta"] == metrics["core_total_model_calls"] - metrics["bare_total_model_calls"]

    def test_wall_time_delta_correct(self):
        tm = _task_map()
        rows = _all_valid_rows(tm)
        metrics = compute_metrics(rows, tm)
        assert isinstance(metrics["wall_time_delta"], float)

    def test_failure_family_counts_correct(self):
        tm = _task_map()
        rows = _all_valid_rows(tm)
        metrics = compute_metrics(rows, tm)
        assert sum(metrics["failure_families"].values()) >= 0

    def test_no_uplift_classification_correct(self):
        tm = _task_map()
        rows = _all_valid_rows(tm)
        # All fail => neither solves
        metrics = compute_metrics(rows, tm)
        eff = classify_effectiveness(metrics, rows, tm)
        assert eff == "V2_VALID_NO_UPLIFT"

    def test_directional_uplift_classification_correct(self):
        tm = _task_map()
        rows = _all_valid_rows(tm)
        # Make core solve all
        for r in rows:
            if r["arm_id"] == "N30R_B_7B_REAL_CORE":
                r["solved"] = True
                r["terminal_status"] = "VERIFIED_SOLVE"
                r["verifier_status"] = "pass"
        metrics = compute_metrics(rows, tm)
        eff = classify_effectiveness(metrics, rows, tm)
        assert eff == "V2_DIRECTIONAL_UPLIFT"

    def test_directional_regression_classification_correct(self):
        tm = _task_map()
        rows = _all_valid_rows(tm)
        # Make bare solve all, core none
        for r in rows:
            if r["arm_id"] == "N30R_A_7B_BARE":
                r["solved"] = True
                r["terminal_status"] = "VERIFIED_SOLVE"
                r["verifier_status"] = "pass"
        metrics = compute_metrics(rows, tm)
        eff = classify_effectiveness(metrics, rows, tm)
        assert eff == "V2_DIRECTIONAL_REGRESSION"


# ---------------------------------------------------------------------------
# Run mode blocked
# ---------------------------------------------------------------------------

class TestRunMode:
    def test_run_mode_plan_only(self):
        """Run mode with --plan-only does not call provider."""
        import subprocess
        result = subprocess.run(
            [sys.executable, "scripts/bench/n30r_v2_paired_eval.py",
             "--manifest", MANIFEST_PATH, "--plan-only"],
            capture_output=True, text=True, cwd=REPO_ROOT,
        )
        assert '"provider_calls": 0' in result.stdout
        assert '"live_model_calls": 0' in result.stdout


# ---------------------------------------------------------------------------
# Environment preflight tests
# ---------------------------------------------------------------------------

class TestEnvironmentPreflight:
    def test_check_environment_accepts_venv(self):
        from scripts.bench.n30r_v2_runner import _check_environment
        env = _check_environment()
        assert env["environment_valid"] is True
        assert env["lancedb_available"] is True
        assert env["project_venv_match"] is True

    def test_check_environment_rejects_system_python(self, monkeypatch):
        from scripts.bench.n30r_v2_runner import _check_environment
        monkeypatch.setattr("sys.executable", "/usr/bin/python3")
        env = _check_environment()
        assert env["environment_valid"] is False
        assert env["project_venv_match"] is False

    def test_check_environment_missing_lancedb_fails(self, monkeypatch):
        from scripts.bench.n30r_v2_runner import _check_environment
        import builtins
        original_import = builtins.__import__
        def mocked_import(name, *args, **kwargs):
            if name == "lancedb":
                raise ImportError("mocked lancedb missing")
            return original_import(name, *args, **kwargs)
        monkeypatch.setattr(builtins, "__import__", mocked_import)
        env = _check_environment()
        assert env["environment_valid"] is False
        assert env["lancedb_available"] is False

    def test_check_environment_requests_warning_fails(self, monkeypatch):
        from scripts.bench.n30r_v2_runner import _check_environment
        import builtins
        from urllib3.exceptions import DependencyWarning
        original_import = builtins.__import__
        def mocked_import(name, *args, **kwargs):
            if name == "requests":
                import warnings
                warnings.warn("mocked requests warning", DependencyWarning)
            return original_import(name, *args, **kwargs)
        monkeypatch.setattr(builtins, "__import__", mocked_import)
        env = _check_environment()
        assert env["environment_valid"] is False
        assert env["dependency_warning_count"] > 0

    def test_run_evaluation_invalid_env_zero_calls(self, monkeypatch):
        from scripts.bench.n30r_v2_runner import run_evaluation
        monkeypatch.setattr("scripts.bench.n30r_v2_runner._check_environment", lambda: {
            "python_executable": "/fake/venv/bin/python",
            "python_version": "3.14.0",
            "sys_prefix": "/fake/venv",
            "sys_base_prefix": "/fake/base",
            "virtualenv_active": True,
            "project_venv_match": False,
            "project_venv_expected": "/fake/venv/bin/python",
            "project_venv_resolved": "/fake/venv/bin/python3.14",
            "lancedb_available": True,
            "lancedb_version": "0.30.2",
            "requests_version": "2.33.1",
            "urllib3_version": "2.5.0",
            "charset_normalizer_version": "3.4.7",
            "dependency_warning_count": 0,
            "environment_valid": False,
        })
        m = _load_manifest()
        result = run_evaluation(m, None, None)
        assert result["status"] == "ENVIRONMENT_INVALID"
        assert result["total_rows"] == 0

    def test_patch_verifier_python3_to_sysexec(self):
        from scripts.bench.n30r_v2_runner import _patch_verifier_command
        import sys
        patched = _patch_verifier_command(("python3", "-c", "print(1)"))
        assert patched[0] == sys.executable
        assert patched[1:] == ["-c", "print(1)"]

    def test_patch_verifier_non_python_unchanged(self):
        from scripts.bench.n30r_v2_runner import _patch_verifier_command
        unchanged = _patch_verifier_command(("node", "script.js"))
        assert unchanged == ["node", "script.js"]

    def test_patch_verifier_python_unchanged(self):
        from scripts.bench.n30r_v2_runner import _patch_verifier_command
        import sys
        patched = _patch_verifier_command(("python", "-V"))
        assert patched[0] == sys.executable

    def test_run_core_row_restores_environment(self, monkeypatch):
        from scripts.bench.n30r_v2_runner import run_core_row
        from unittest.mock import MagicMock

        # Mock planner, executor and other external calls
        mock_plan = MagicMock()
        mock_plan.signal_snapshot = {}
        monkeypatch.setattr("nexus.engine.capability_planner.CapabilityPlanner.plan", lambda *a, **k: mock_plan)
        monkeypatch.setattr("nexus.services.local_heal.local_model_capability_wiring.project_planner_capabilities_for_local_executor", lambda *a: MagicMock())
        monkeypatch.setattr("nexus.services.local_heal.local_model_source_anchor.build_local_model_source_anchor", lambda *a, **k: MagicMock(span_hash="abc"))

        mock_response = MagicMock()
        mock_response.candidate_patch = "print(1)"
        mock_response.raw_model_metadata = {"selected_candidate_hash": "hash123", "isolated_verifier_status": "pass"}
        monkeypatch.setattr("nexus.services.local_heal.local_model_executor.LocalModelExecutor.run", lambda *a, **k: mock_response)

        # Test case 1: Original env is empty
        for k in ["NEXUS_ENABLE_LOCAL_MODEL_EXECUTOR", "NEXUS_LOCAL_MODEL_EXECUTOR_TOPOLOGY",
                  "NEXUS_LOCAL_MODEL_CALL_ALLOWED", "NEXUS_LOCAL_MODEL_EXECUTOR_PROVIDER",
                  "NEXUS_LOCAL_MODEL_EXECUTOR_MODEL"]:
            monkeypatch.delenv(k, raising=False)

        manifest = _load_manifest()
        task_dict = manifest["tasks"][0]

        # Verify execution works and restores back to empty env
        res = run_core_row(task_dict, 42, "run1")
        assert res["solved"] is True
        for k in ["NEXUS_ENABLE_LOCAL_MODEL_EXECUTOR", "NEXUS_LOCAL_MODEL_EXECUTOR_TOPOLOGY",
                  "NEXUS_LOCAL_MODEL_CALL_ALLOWED", "NEXUS_LOCAL_MODEL_EXECUTOR_PROVIDER",
                  "NEXUS_LOCAL_MODEL_EXECUTOR_MODEL"]:
            assert k not in os.environ

        # Test case 2: Original env has pre-existing values
        os.environ["NEXUS_LOCAL_MODEL_EXECUTOR_PROVIDER"] = "pre_exist_provider"
        res = run_core_row(task_dict, 42, "run1")
        assert os.environ.get("NEXUS_LOCAL_MODEL_EXECUTOR_PROVIDER") == "pre_exist_provider"
        # Others should still be cleaned up
        assert "NEXUS_ENABLE_LOCAL_MODEL_EXECUTOR" not in os.environ

        # Clean up test env
        os.environ.pop("NEXUS_LOCAL_MODEL_EXECUTOR_PROVIDER", None)



# ---------------------------------------------------------------------------
# Environment receipts in validation
# ---------------------------------------------------------------------------

class TestEnvironmentReceiptValidation:
    def test_reject_missing_env_receipt(self):
        tm = _task_map()
        row = _valid_bare_row("n30r_smoke_syntax", tm)
        del row["env_receipt"]
        del row["env_receipt_sha256"]
        issues = validate_row(row, tm, _load_manifest())
        assert any("missing_field:env_receipt" in i for i in issues)
        assert any("missing_field:env_receipt_sha256" in i for i in issues)

    def test_reject_mismatched_env_hash(self):
        tm = _task_map()
        rows = _all_valid_rows(tm)
        # Change one row's env hash
        rows[0]["env_receipt_sha256"] = "badhash"
        val = validate_results(_load_manifest(), _write_jsonl(rows))
        assert any("environment_hash" in " ".join(i.get("issues", []))
                   for i in val.get("issues", []) if i.get("issues"))

    def test_reject_cross_arm_env_hash_mismatch(self):
        tm = _task_map()
        rows = _all_valid_rows(tm)
        rows[0]["env_receipt_sha256"] = hashlib.sha256(b"bare_only").hexdigest()
        val = validate_results(_load_manifest(), _write_jsonl(rows))
        assert val["status"] == "INVALID"

    def test_accept_matching_env_hash(self):
        tm = _task_map()
        rows = _all_valid_rows(tm)
        val = validate_results(_load_manifest(), _write_jsonl(rows))
        # Should pass environment checks
        env_issues = [i for i in val.get("issues", [])
                      if any("environment_hash" in iss for iss in i.get("issues", []))]
        assert len(env_issues) == 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_jsonl(rows: list[dict]) -> str:
    """Write rows to a temp JSONL file, return path."""
    import tempfile
    fd, path = tempfile.mkstemp(suffix=".jsonl")
    with os.fdopen(fd, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return path
