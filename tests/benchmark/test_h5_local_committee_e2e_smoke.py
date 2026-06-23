"""Tests for H5-14 local committee E2E smoke harness."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_h5_14_dry_run_smoke_returns_pass_no_side_effects():
    """H5-14 Test 1: dry-run smoke returns pass and no side effects."""
    from scripts.bench.h5_local_committee_e2e_smoke import run_h5_local_committee_e2e_smoke

    repo_root = Path(__file__).resolve().parents[2]
    result = run_h5_local_committee_e2e_smoke(repo_root, dry_run=True)

    assert result["schema"] == "nexus.h5_local_committee_e2e_smoke.v1"
    assert result["status"] == "pass"
    assert result["dry_run"] is True
    assert result["local_committee_invoked"] is False
    assert result["final_source_changed"] is False
    assert result["final_patch_replaced"] is False
    assert result["output_mutated"] is False
    assert result["model_calls_incremented"] is False
    assert result["public_claim_allowed"] is False
    assert result["production_ready"] is False


def test_h5_14_cli_dry_run_outputs_json():
    """H5-14 Test 2: CLI dry-run outputs JSON."""
    script = Path(__file__).resolve().parents[2] / "scripts" / "bench" / "h5_local_committee_e2e_smoke.py"
    result = subprocess.run(
        [sys.executable, str(script), "--dry-run"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["schema"] == "nexus.h5_local_committee_e2e_smoke.v1"
    assert data["status"] == "pass"
    assert data["dry_run"] is True


def test_h5_14_unavailable_runtime_returns_skipped(monkeypatch):
    """H5-14 Test 3: unavailable runtime returns skipped, not fake pass."""
    from scripts.bench.h5_local_committee_e2e_smoke import run_h5_local_committee_e2e_smoke, _detect_local_committee_runtime

    def _fake_detect(repo_root):
        return False, "local_committee_runtime_unavailable"

    monkeypatch.setattr("scripts.bench.h5_local_committee_e2e_smoke._detect_local_committee_runtime", _fake_detect)

    repo_root = Path(__file__).resolve().parents[2]
    result = run_h5_local_committee_e2e_smoke(repo_root, dry_run=False)

    assert result["status"] == "skipped"
    assert result["skipped_reason"] != ""
    assert result["local_committee_invoked"] is False
    assert result["final_source_changed"] is False


def test_h5_14_no_production_files_modified():
    """H5-14 Test 4: dry-run creates no runtime artifacts."""
    from scripts.bench.h5_local_committee_e2e_smoke import run_h5_local_committee_e2e_smoke

    repo_root = Path(__file__).resolve().parents[2]
    result = run_h5_local_committee_e2e_smoke(repo_root, dry_run=True)

    assert result["status"] == "pass"
    assert result["final_source_changed"] is False
    assert result["final_patch_replaced"] is False
    assert result["output_mutated"] is False
    assert result["model_calls_incremented"] is False


def test_h5_14_result_schema_contains_required_fields():
    """H5-14 Test 5: result schema contains all required fields."""
    from scripts.bench.h5_local_committee_e2e_smoke import run_h5_local_committee_e2e_smoke

    repo_root = Path(__file__).resolve().parents[2]
    result = run_h5_local_committee_e2e_smoke(repo_root, dry_run=True)

    required = [
        "schema", "status", "skipped_reason", "dry_run",
        "local_committee_invoked", "candidate_count",
        "selected_candidate_id", "selected_candidate_applied",
        "selected_candidate_hash_match", "selected_candidate_patch_sha256",
        "selected_candidate_patch_length", "local_solve_eligible",
        "final_source_changed", "final_patch_replaced", "output_mutated",
        "model_calls_incremented", "public_claim_allowed", "production_ready",
        "evidence",
    ]
    for key in required:
        assert key in result, f"missing key: {key}"
