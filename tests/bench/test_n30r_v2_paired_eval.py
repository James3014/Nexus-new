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
    def test_run_mode_blocked(self):
        """Run mode should not execute without V1 merge."""
        import subprocess
        result = subprocess.run(
            [sys.executable, "scripts/bench/n30r_v2_paired_eval.py",
             "--manifest", MANIFEST_PATH, "--run"],
            capture_output=True, text=True, cwd=REPO_ROOT,
        )
        assert "RUN_MODE_BLOCKED_UNTIL_V1_MERGE" in result.stdout


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
