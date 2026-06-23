"""Tests for H5-14/H5-15 local committee E2E smoke harness and receipt adapter."""
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
    assert "receipt" in data


def test_h5_14_unavailable_runtime_returns_skipped(monkeypatch):
    """H5-14 Test 3: unavailable runtime returns skipped, not fake pass."""
    from scripts.bench.h5_local_committee_e2e_smoke import run_h5_local_committee_e2e_smoke

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


def test_h5_15_dry_run_result_includes_receipt_and_not_h5_compatible():
    """H5-15 Test 1: dry-run result includes receipt and remains not H5-compatible."""
    from scripts.bench.h5_local_committee_e2e_smoke import run_h5_local_committee_e2e_smoke

    repo_root = Path(__file__).resolve().parents[2]
    result = run_h5_local_committee_e2e_smoke(repo_root, dry_run=True)

    receipt = result["receipt"]
    assert receipt["schema"] == "nexus.h5_local_committee_smoke_receipt.v1"
    assert receipt["h5_compatible"] is False
    assert receipt["h5_local_finalization_candidate_ready"] is False
    assert receipt["h5_local_finalization_blocked_reason"] == "dry_run_no_candidate"
    assert receipt["final_source_changed"] is False
    assert receipt["production_ready"] is False


def test_h5_15_skipped_runtime_maps_to_blocked_receipt(monkeypatch):
    """H5-15 Test 2: skipped runtime maps to blocked receipt."""
    from scripts.bench.h5_local_committee_e2e_smoke import run_h5_local_committee_e2e_smoke

    def _fake_detect(repo_root):
        return False, "local_committee_runtime_unavailable"

    monkeypatch.setattr("scripts.bench.h5_local_committee_e2e_smoke._detect_local_committee_runtime", _fake_detect)

    repo_root = Path(__file__).resolve().parents[2]
    result = run_h5_local_committee_e2e_smoke(repo_root, dry_run=False)

    receipt = result["receipt"]
    assert receipt["status"] == "skipped"
    assert receipt["runtime_available"] is False
    assert receipt["h5_compatible"] is False
    assert receipt["h5_local_finalization_blocked_reason"] != ""


def test_h5_15_synthetic_complete_invoked_smoke_maps_to_h5_compatible():
    """H5-15 Test 3: synthetic complete invoked smoke maps to H5-compatible receipt."""
    from scripts.bench.h5_local_committee_e2e_smoke import build_h5_local_committee_smoke_receipt

    smoke = {
        "status": "pass",
        "dry_run": False,
        "local_committee_invoked": True,
        "candidate_count": 1,
        "selected_candidate_id": "C_1#candidate-0",
        "selected_candidate_applied": True,
        "selected_candidate_hash_match": True,
        "selected_candidate_patch_sha256": "abc123",
        "selected_candidate_patch_length": 123,
        "local_solve_eligible": True,
    }
    receipt = build_h5_local_committee_smoke_receipt(smoke)
    assert receipt["h5_compatible"] is True
    assert receipt["h5_local_finalization_candidate_ready"] is True
    assert receipt["h5_local_finalization_blocked_reason"] == ""


def test_h5_15_synthetic_missing_patch_hash_blocks():
    """H5-15 Test 4: synthetic missing patch hash blocks."""
    from scripts.bench.h5_local_committee_e2e_smoke import build_h5_local_committee_smoke_receipt

    smoke = {
        "status": "pass",
        "dry_run": False,
        "local_committee_invoked": True,
        "candidate_count": 1,
        "selected_candidate_id": "C_1#candidate-0",
        "selected_candidate_applied": True,
        "selected_candidate_hash_match": True,
        "selected_candidate_patch_sha256": "",
        "selected_candidate_patch_length": 123,
        "local_solve_eligible": True,
    }
    receipt = build_h5_local_committee_smoke_receipt(smoke)
    assert receipt["h5_compatible"] is False
    assert receipt["h5_local_finalization_blocked_reason"] == "missing_selected_candidate_patch_sha256"


def test_h5_15_synthetic_solve_not_eligible_blocks():
    """H5-15 Test 5: synthetic solve not eligible blocks."""
    from scripts.bench.h5_local_committee_e2e_smoke import build_h5_local_committee_smoke_receipt

    smoke = {
        "status": "pass",
        "dry_run": False,
        "local_committee_invoked": True,
        "candidate_count": 1,
        "selected_candidate_id": "C_1#candidate-0",
        "selected_candidate_applied": True,
        "selected_candidate_hash_match": True,
        "selected_candidate_patch_sha256": "abc123",
        "selected_candidate_patch_length": 123,
        "local_solve_eligible": False,
    }
    receipt = build_h5_local_committee_smoke_receipt(smoke)
    assert receipt["h5_compatible"] is False
    assert receipt["h5_local_finalization_blocked_reason"] == "local_solve_not_eligible"


def test_h5_15_cli_dry_run_includes_receipt():
    """H5-15 Test 6: CLI dry-run includes receipt."""
    script = Path(__file__).resolve().parents[2] / "scripts" / "bench" / "h5_local_committee_e2e_smoke.py"
    result = subprocess.run(
        [sys.executable, str(script), "--dry-run"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert "receipt" in data
    assert data["receipt"]["schema"] == "nexus.h5_local_committee_smoke_receipt.v1"


def test_h5_15_safety_invariants_remain_false():
    """H5-15 Test 7: safety invariants remain false."""
    from scripts.bench.h5_local_committee_e2e_smoke import build_h5_local_committee_smoke_receipt

    for dry in [True, False]:
        for inv in [True, False]:
            smoke = {"status": "pass", "dry_run": dry, "local_committee_invoked": inv}
            receipt = build_h5_local_committee_smoke_receipt(smoke)
            assert receipt["final_source_changed"] is False
            assert receipt["final_patch_replaced"] is False
            assert receipt["output_mutated"] is False
            assert receipt["model_calls_incremented"] is False
            assert receipt["public_claim_allowed"] is False
            assert receipt["production_ready"] is False
