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


def test_h5_16_dry_run_readiness_bridge_blocks():
    """H5-16 Test 1: dry-run readiness bridge blocks."""
    from scripts.bench.h5_local_committee_e2e_smoke import run_h5_local_committee_e2e_smoke

    repo_root = Path(__file__).resolve().parents[2]
    result = run_h5_local_committee_e2e_smoke(repo_root, dry_run=True)

    bridge = result["readiness_bridge"]
    assert bridge["readiness_status"] == "blocked"
    assert "dry_run_no_real_candidate" in bridge["readiness_reasons"]
    assert bridge["local_committee_e2e_ready_shadow"] is False
    assert bridge["can_feed_h5_readiness_shadow"] is False


def test_h5_16_skipped_smoke_readiness_bridge_blocks(monkeypatch):
    """H5-16 Test 2: skipped smoke readiness bridge blocks."""
    from scripts.bench.h5_local_committee_e2e_smoke import run_h5_local_committee_e2e_smoke

    def _fake_detect(repo_root):
        return False, "local_committee_runtime_unavailable"

    monkeypatch.setattr("scripts.bench.h5_local_committee_e2e_smoke._detect_local_committee_runtime", _fake_detect)

    repo_root = Path(__file__).resolve().parents[2]
    result = run_h5_local_committee_e2e_smoke(repo_root, dry_run=False)

    bridge = result["readiness_bridge"]
    assert bridge["readiness_status"] == "blocked"
    assert "smoke_skipped" in bridge["readiness_reasons"]


def test_h5_16_synthetic_complete_receipt_produces_ready_shadow():
    """H5-16 Test 3: synthetic complete receipt produces ready_shadow."""
    from scripts.bench.h5_local_committee_e2e_smoke import build_h5_local_committee_readiness_bridge

    receipt = {
        "status": "pass",
        "dry_run": False,
        "h5_compatible": True,
        "selected_candidate_id": "C_1#candidate-0",
        "selected_candidate_applied": True,
        "selected_candidate_hash_match": True,
        "selected_candidate_patch_sha256": "abc123",
        "selected_candidate_patch_length": 123,
        "local_solve_eligible": True,
    }
    bridge = build_h5_local_committee_readiness_bridge(receipt)
    assert bridge["readiness_status"] == "ready_shadow"
    assert bridge["local_committee_e2e_ready_shadow"] is True
    assert bridge["can_feed_h5_readiness_shadow"] is True
    assert bridge["candidate_identity_ready"] is True
    assert bridge["candidate_application_ready"] is True
    assert bridge["candidate_hash_ready"] is True
    assert bridge["candidate_patch_metadata_ready"] is True
    assert bridge["local_solve_ready"] is True


def test_h5_16_missing_candidate_id_blocks_identity_readiness():
    """H5-16 Test 4: missing candidate id blocks identity readiness."""
    from scripts.bench.h5_local_committee_e2e_smoke import build_h5_local_committee_readiness_bridge

    receipt = {
        "status": "pass",
        "dry_run": False,
        "h5_compatible": True,
        "selected_candidate_id": "",
        "selected_candidate_applied": True,
        "selected_candidate_hash_match": True,
        "selected_candidate_patch_sha256": "abc123",
        "selected_candidate_patch_length": 123,
        "local_solve_eligible": True,
    }
    bridge = build_h5_local_committee_readiness_bridge(receipt)
    assert bridge["candidate_identity_ready"] is False
    assert bridge["readiness_status"] == "blocked"


def test_h5_16_missing_patch_metadata_blocks_patch_readiness():
    """H5-16 Test 5: missing patch metadata blocks patch readiness."""
    from scripts.bench.h5_local_committee_e2e_smoke import build_h5_local_committee_readiness_bridge

    receipt = {
        "status": "pass",
        "dry_run": False,
        "h5_compatible": True,
        "selected_candidate_id": "C_1#candidate-0",
        "selected_candidate_applied": True,
        "selected_candidate_hash_match": True,
        "selected_candidate_patch_sha256": "",
        "selected_candidate_patch_length": 0,
        "local_solve_eligible": True,
    }
    bridge = build_h5_local_committee_readiness_bridge(receipt)
    assert bridge["candidate_patch_metadata_ready"] is False
    assert bridge["readiness_status"] == "blocked"


def test_h5_16_solve_not_eligible_blocks_local_solve_readiness():
    """H5-16 Test 6: solve not eligible blocks local solve readiness."""
    from scripts.bench.h5_local_committee_e2e_smoke import build_h5_local_committee_readiness_bridge

    receipt = {
        "status": "pass",
        "dry_run": False,
        "h5_compatible": True,
        "selected_candidate_id": "C_1#candidate-0",
        "selected_candidate_applied": True,
        "selected_candidate_hash_match": True,
        "selected_candidate_patch_sha256": "abc123",
        "selected_candidate_patch_length": 123,
        "local_solve_eligible": False,
    }
    bridge = build_h5_local_committee_readiness_bridge(receipt)
    assert bridge["local_solve_ready"] is False
    assert bridge["readiness_status"] == "blocked"


def test_h5_16_safety_invariants_remain_false():
    """H5-16 Test 7: safety invariants remain false."""
    from scripts.bench.h5_local_committee_e2e_smoke import build_h5_local_committee_readiness_bridge

    bridges = [
        {},
        {"status": "skipped", "dry_run": True},
        {"status": "pass", "dry_run": False, "h5_compatible": True, "selected_candidate_id": "C_1#candidate-0",
         "selected_candidate_applied": True, "selected_candidate_hash_match": True,
         "selected_candidate_patch_sha256": "abc", "selected_candidate_patch_length": 1,
         "local_solve_eligible": True},
    ]
    for b in bridges:
        bridge = build_h5_local_committee_readiness_bridge(b)
        assert bridge["final_source_changed"] is False
        assert bridge["final_patch_replaced"] is False
        assert bridge["output_mutated"] is False
        assert bridge["model_calls_incremented"] is False
        assert bridge["public_claim_allowed"] is False
        assert bridge["production_ready"] is False


def test_h5_16_cli_dry_run_includes_readiness_bridge():
    """H5-16 Test 8: CLI dry-run includes readiness_bridge."""
    script = Path(__file__).resolve().parents[2] / "scripts" / "bench" / "h5_local_committee_e2e_smoke.py"
    result = subprocess.run(
        [sys.executable, str(script), "--dry-run"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert "readiness_bridge" in data
    assert data["readiness_bridge"]["schema"] == "nexus.h5_local_committee_readiness_bridge.v1"
    assert data["readiness_bridge"]["readiness_status"] == "blocked"


def test_h5_17_dry_run_output_includes_evidence_bundle():
    """H5-17 Test 1: dry-run output includes evidence_bundle."""
    from scripts.bench.h5_local_committee_e2e_smoke import run_h5_local_committee_e2e_smoke

    repo_root = Path(__file__).resolve().parents[2]
    result = run_h5_local_committee_e2e_smoke(repo_root, dry_run=True)

    bundle = result["evidence_bundle"]
    assert bundle["schema"] == "nexus.h5_local_committee_smoke_evidence_bundle.v1"
    assert bundle["bundle_status"] == "blocked"
    assert bundle["can_feed_h5_readiness_shadow"] is False
    assert any("dry_run" in r for r in bundle["blocked_reasons"])


def test_h5_17_skipped_smoke_maps_to_skipped_bundle(monkeypatch):
    """H5-17 Test 2: skipped smoke maps to skipped bundle."""
    from scripts.bench.h5_local_committee_e2e_smoke import run_h5_local_committee_e2e_smoke

    def _fake_detect(repo_root):
        return False, "local_committee_runtime_unavailable"

    monkeypatch.setattr("scripts.bench.h5_local_committee_e2e_smoke._detect_local_committee_runtime", _fake_detect)

    repo_root = Path(__file__).resolve().parents[2]
    result = run_h5_local_committee_e2e_smoke(repo_root, dry_run=False)

    bundle = result["evidence_bundle"]
    assert bundle["bundle_status"] == "blocked"
    assert bundle["can_feed_h5_readiness_shadow"] is False
    assert len(bundle["blocked_reasons"]) > 0


def test_h5_17_synthetic_ready_shadow_maps_to_pass_bundle():
    """H5-17 Test 3: synthetic ready shadow maps to pass bundle."""
    from scripts.bench.h5_local_committee_e2e_smoke import build_h5_local_committee_smoke_evidence_bundle

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
    from scripts.bench.h5_local_committee_e2e_smoke import build_h5_local_committee_smoke_receipt, build_h5_local_committee_readiness_bridge
    receipt = build_h5_local_committee_smoke_receipt(smoke)
    bridge = build_h5_local_committee_readiness_bridge(receipt)
    smoke["receipt"] = receipt
    smoke["readiness_bridge"] = bridge

    bundle = build_h5_local_committee_smoke_evidence_bundle(smoke)
    assert bundle["bundle_status"] == "pass"
    assert bundle["can_feed_h5_readiness_shadow"] is True
    assert bundle["blocked_reasons"] == []


def test_h5_17_missing_receipt_blocks():
    """H5-17 Test 4: missing receipt blocks."""
    from scripts.bench.h5_local_committee_e2e_smoke import build_h5_local_committee_smoke_evidence_bundle

    smoke = {"status": "pass", "dry_run": False}
    bundle = build_h5_local_committee_smoke_evidence_bundle(smoke)
    assert bundle["bundle_status"] == "blocked"
    assert "missing_smoke_receipt" in bundle["blocked_reasons"]


def test_h5_17_missing_readiness_bridge_blocks():
    """H5-17 Test 5: missing readiness bridge blocks."""
    from scripts.bench.h5_local_committee_e2e_smoke import build_h5_local_committee_smoke_evidence_bundle, build_h5_local_committee_smoke_receipt

    smoke = {
        "status": "pass",
        "dry_run": False,
        "local_committee_invoked": True,
        "candidate_count": 1,
        "selected_candidate_id": "C_1#candidate-0",
        "selected_candidate_applied": True,
        "selected_candidate_hash_match": True,
        "selected_candidate_patch_sha256": "abc",
        "selected_candidate_patch_length": 1,
        "local_solve_eligible": True,
    }
    smoke["receipt"] = build_h5_local_committee_smoke_receipt(smoke)
    bundle = build_h5_local_committee_smoke_evidence_bundle(smoke)
    assert bundle["bundle_status"] == "blocked"
    assert "missing_readiness_bridge" in bundle["blocked_reasons"]


def test_h5_17_safety_invariant_violation_blocks():
    """H5-17 Test 6: safety invariant violation blocks."""
    from scripts.bench.h5_local_committee_e2e_smoke import build_h5_local_committee_smoke_evidence_bundle

    smoke = {"status": "pass", "dry_run": False, "final_source_changed": True}
    bundle = build_h5_local_committee_smoke_evidence_bundle(smoke)
    assert bundle["bundle_status"] == "blocked"
    assert "safety_invariant_violation" in bundle["blocked_reasons"]
    assert bundle["can_feed_h5_readiness_shadow"] is False


def test_h5_17_governance_always_false():
    """H5-17 Test 7: governance always false."""
    from scripts.bench.h5_local_committee_e2e_smoke import build_h5_local_committee_smoke_evidence_bundle

    for smoke in [{}, {"status": "skipped", "dry_run": True}, {"status": "pass", "dry_run": True}]:
        bundle = build_h5_local_committee_smoke_evidence_bundle(smoke)
        assert bundle["governance"]["public_claim_allowed"] is False
        assert bundle["governance"]["production_ready"] is False
        assert bundle["governance"]["internal_only"] is True


def test_h5_17_cli_dry_run_includes_evidence_bundle():
    """H5-17 Test 8: CLI dry-run includes evidence_bundle."""
    script = Path(__file__).resolve().parents[2] / "scripts" / "bench" / "h5_local_committee_e2e_smoke.py"
    result = subprocess.run(
        [sys.executable, str(script), "--dry-run"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert "evidence_bundle" in data
    assert data["evidence_bundle"]["schema"] == "nexus.h5_local_committee_smoke_evidence_bundle.v1"
    assert data["evidence_bundle"]["bundle_status"] == "blocked"


def test_h5_18_dry_run_bundle_rejected():
    """H5-18 Test 1: dry-run bundle rejected."""
    from scripts.bench.h5_local_committee_e2e_smoke import run_h5_local_committee_e2e_smoke

    repo_root = Path(__file__).resolve().parents[2]
    result = run_h5_local_committee_e2e_smoke(repo_root, dry_run=True)

    val = result["ingestion_validation"]
    assert val["validation_status"] == "rejected"
    assert val["accepted_for_h5_readiness_shadow"] is False
    assert any("bundle_not_pass" in r or "cannot_feed_h5_readiness_shadow" in r for r in val["validation_reasons"])


def test_h5_18_skipped_bundle_rejected(monkeypatch):
    """H5-18 Test 2: skipped bundle rejected."""
    from scripts.bench.h5_local_committee_e2e_smoke import run_h5_local_committee_e2e_smoke

    def _fake_detect(repo_root):
        return False, "local_committee_runtime_unavailable"

    monkeypatch.setattr("scripts.bench.h5_local_committee_e2e_smoke._detect_local_committee_runtime", _fake_detect)

    repo_root = Path(__file__).resolve().parents[2]
    result = run_h5_local_committee_e2e_smoke(repo_root, dry_run=False)

    val = result["ingestion_validation"]
    assert val["validation_status"] == "rejected"
    assert val["accepted_for_h5_readiness_shadow"] is False


def test_h5_18_synthetic_pass_bundle_accepted():
    """H5-18 Test 3: synthetic pass bundle accepted."""
    from scripts.bench.h5_local_committee_e2e_smoke import (
        build_h5_local_committee_smoke_receipt,
        build_h5_local_committee_readiness_bridge,
        build_h5_local_committee_smoke_evidence_bundle,
        validate_h5_local_committee_evidence_bundle,
    )

    smoke = {
        "status": "pass", "dry_run": False, "local_committee_invoked": True,
        "candidate_count": 1, "selected_candidate_id": "C_1#candidate-0",
        "selected_candidate_applied": True, "selected_candidate_hash_match": True,
        "selected_candidate_patch_sha256": "abc123", "selected_candidate_patch_length": 123,
        "local_solve_eligible": True,
    }
    receipt = build_h5_local_committee_smoke_receipt(smoke)
    bridge = build_h5_local_committee_readiness_bridge(receipt)
    smoke["receipt"] = receipt
    smoke["readiness_bridge"] = bridge
    bundle = build_h5_local_committee_smoke_evidence_bundle(smoke)

    val = validate_h5_local_committee_evidence_bundle(bundle)
    assert val["validation_status"] == "accepted"
    assert val["accepted_for_h5_readiness_shadow"] is True
    assert val["validation_reasons"] == []


def test_h5_18_wrong_schema_rejected():
    """H5-18 Test 4: wrong schema rejected."""
    from scripts.bench.h5_local_committee_e2e_smoke import validate_h5_local_committee_evidence_bundle

    val = validate_h5_local_committee_evidence_bundle({"schema": "wrong"})
    assert val["validation_status"] == "rejected"
    assert "invalid_bundle_schema" in val["validation_reasons"]


def test_h5_18_safety_violation_rejected():
    """H5-18 Test 5: safety invariant violation rejected."""
    from scripts.bench.h5_local_committee_e2e_smoke import validate_h5_local_committee_evidence_bundle

    bundle = {"schema": "nexus.h5_local_committee_smoke_evidence_bundle.v1",
              "safety": {"output_mutated": True}}
    val = validate_h5_local_committee_evidence_bundle(bundle)
    assert val["validation_status"] == "rejected"
    assert "safety_invariant_violation" in val["validation_reasons"]


def test_h5_18_governance_violation_rejected():
    """H5-18 Test 6: governance violation rejected."""
    from scripts.bench.h5_local_committee_e2e_smoke import validate_h5_local_committee_evidence_bundle

    bundle = {"schema": "nexus.h5_local_committee_smoke_evidence_bundle.v1",
              "governance": {"production_ready": True}}
    val = validate_h5_local_committee_evidence_bundle(bundle)
    assert val["validation_status"] == "rejected"
    assert "governance_boundary_violation" in val["validation_reasons"]


def test_h5_18_receipt_not_compatible_rejected():
    """H5-18 Test 7: receipt not compatible rejected."""
    from scripts.bench.h5_local_committee_e2e_smoke import validate_h5_local_committee_evidence_bundle

    bundle = {"schema": "nexus.h5_local_committee_smoke_evidence_bundle.v1",
              "receipt": {"schema": "nexus.h5_local_committee_smoke_receipt.v1", "h5_compatible": False}}
    val = validate_h5_local_committee_evidence_bundle(bundle)
    assert val["validation_status"] == "rejected"
    assert "receipt_not_h5_compatible" in val["validation_reasons"]


def test_h5_18_readiness_bridge_not_ready_rejected():
    """H5-18 Test 8: readiness bridge not ready rejected."""
    from scripts.bench.h5_local_committee_e2e_smoke import validate_h5_local_committee_evidence_bundle

    bundle = {"schema": "nexus.h5_local_committee_smoke_evidence_bundle.v1",
              "readiness_bridge": {"schema": "nexus.h5_local_committee_readiness_bridge.v1",
                                   "readiness_status": "blocked"}}
    val = validate_h5_local_committee_evidence_bundle(bundle)
    assert val["validation_status"] == "rejected"
    assert "readiness_bridge_not_ready" in val["validation_reasons"]


def test_h5_18_helper_purity():
    """H5-18 Test 9: helper purity."""
    import copy
    from scripts.bench.h5_local_committee_e2e_smoke import validate_h5_local_committee_evidence_bundle

    bundle = {"schema": "nexus.h5_local_committee_smoke_evidence_bundle.v1"}
    original = copy.deepcopy(bundle)
    validate_h5_local_committee_evidence_bundle(bundle)
    assert bundle == original


def test_h5_18_cli_dry_run_includes_ingestion_validation():
    """H5-18 Test 10: CLI dry-run includes ingestion_validation."""
    script = Path(__file__).resolve().parents[2] / "scripts" / "bench" / "h5_local_committee_e2e_smoke.py"
    result = subprocess.run(
        [sys.executable, str(script), "--dry-run"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert "ingestion_validation" in data
    assert data["ingestion_validation"]["schema"] == "nexus.h5_local_committee_evidence_ingestion_validation.v1"
    assert data["ingestion_validation"]["validation_status"] == "rejected"
