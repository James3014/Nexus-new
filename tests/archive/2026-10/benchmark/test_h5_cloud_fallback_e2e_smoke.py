"""Tests for H5-20 cloud fallback E2E smoke harness."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_h5_20_dry_run_returns_pass_and_no_provider_call():
    """H5-20 Test 1: dry-run returns pass and no provider call."""
    from scripts.bench.h5_cloud_fallback_e2e_smoke import run_h5_cloud_fallback_e2e_smoke

    result = run_h5_cloud_fallback_e2e_smoke(provider="gemini", dry_run=True)
    assert result["schema"] == "nexus.h5_cloud_fallback_e2e_smoke.v1"
    assert result["status"] == "pass"
    assert result["cloud_fallback_would_invoke"] is True
    assert result["cloud_fallback_invoked"] is False
    assert result["cloud_model_invoked"] is False
    assert result["model_calls_incremented"] is False
    assert result["model_calls_after_shadow"] == 1
    assert result["final_source_changed"] is False
    assert result["final_patch_replaced"] is False
    assert result["output_mutated"] is False


def test_h5_20_run_without_allow_real_call_skips():
    """H5-20 Test 2: run without allow_real_call skips."""
    from scripts.bench.h5_cloud_fallback_e2e_smoke import run_h5_cloud_fallback_e2e_smoke

    result = run_h5_cloud_fallback_e2e_smoke(provider="gemini", dry_run=False, allow_real_call=False)
    assert result["status"] == "skipped"
    assert result["skipped_reason"] == "real_cloud_call_not_allowed"
    assert result["cloud_fallback_invoked"] is False
    assert result["cloud_model_invoked"] is False
    assert result["model_calls_incremented"] is False


def test_h5_20_env_not_enabled_skips():
    """H5-20 Test 3: env not enabled skips."""
    from scripts.bench.h5_cloud_fallback_e2e_smoke import run_h5_cloud_fallback_e2e_smoke

    result = run_h5_cloud_fallback_e2e_smoke(provider="gemini", dry_run=False, allow_real_call=True)
    assert result["status"] == "skipped"
    assert result["skipped_reason"] == "real_cloud_call_env_not_enabled"


def test_h5_20_unsupported_provider_skips():
    """H5-20 Test 4: unsupported provider skips."""
    from scripts.bench.h5_cloud_fallback_e2e_smoke import run_h5_cloud_fallback_e2e_smoke

    result = run_h5_cloud_fallback_e2e_smoke(provider="unknown", dry_run=True)
    assert result["status"] == "skipped"
    assert result["skipped_reason"] == "unsupported_provider"


def test_h5_20_cli_dry_run_outputs_json():
    """H5-20 Test 5: CLI dry-run outputs JSON."""
    script = Path(__file__).resolve().parents[2] / "scripts" / "bench" / "h5_cloud_fallback_e2e_smoke.py"
    result = subprocess.run(
        [sys.executable, str(script), "--dry-run", "--provider", "gemini"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["schema"] == "nexus.h5_cloud_fallback_e2e_smoke.v1"
    assert data["status"] == "pass"
    assert data["provider"] == "gemini"


def test_h5_20_result_schema_contains_required_fields():
    """H5-20 Test 6: result schema contains all required fields."""
    from scripts.bench.h5_cloud_fallback_e2e_smoke import run_h5_cloud_fallback_e2e_smoke

    result = run_h5_cloud_fallback_e2e_smoke(provider="gemini", dry_run=True)

    required = [
        "schema", "status", "skipped_reason", "provider", "dry_run",
        "allow_real_call", "real_call_env_enabled",
        "cloud_fallback_would_invoke", "cloud_fallback_invoked", "cloud_model_invoked",
        "cloud_output_captured", "cloud_output_verified",
        "model_calls_before", "model_calls_after_shadow", "model_calls_incremented",
        "final_source_changed", "final_patch_replaced", "output_mutated",
        "public_claim_allowed", "production_ready", "evidence",
    ]
    for key in required:
        assert key in result, f"missing key: {key}"


def test_h5_20_safety_invariants_remain_false():
    """H5-20 Test 7: safety invariants remain false."""
    from scripts.bench.h5_cloud_fallback_e2e_smoke import run_h5_cloud_fallback_e2e_smoke

    for provider in ["gemini", "codex"]:
        result = run_h5_cloud_fallback_e2e_smoke(provider=provider, dry_run=True)
        assert result["final_source_changed"] is False
        assert result["final_patch_replaced"] is False
        assert result["output_mutated"] is False
        assert result["model_calls_incremented"] is False
        assert result["public_claim_allowed"] is False
        assert result["production_ready"] is False


def test_h5_20_no_capability_runner_import():
    """H5-20 Test 8: no capability runner import or mutation."""
    smoke_path = Path(__file__).resolve().parents[2] / "scripts" / "bench" / "h5_cloud_fallback_e2e_smoke.py"
    content = smoke_path.read_text(encoding="utf-8")
    assert "capability_ab_runner" not in content


def test_h5_21_dry_run_includes_receipt_and_bridge_both_blocked():
    """H5-21 Test 1: dry-run includes receipt and bridge, both blocked."""
    from scripts.bench.h5_cloud_fallback_e2e_smoke import run_h5_cloud_fallback_e2e_smoke

    result = run_h5_cloud_fallback_e2e_smoke(provider="gemini", dry_run=True)

    receipt = result["receipt"]
    assert receipt["schema"] == "nexus.h5_cloud_fallback_smoke_receipt.v1"
    assert receipt["h5_cloud_fallback_compatible"] is False

    bridge = result["readiness_bridge"]
    assert bridge["schema"] == "nexus.h5_cloud_fallback_readiness_bridge.v1"
    assert bridge["can_feed_h5_readiness_shadow"] is False
    assert any("dry_run_no_real_cloud_output" in r for r in bridge["readiness_reasons"])


def test_h5_21_skipped_unsupported_provider_maps_to_blocked():
    """H5-21 Test 2: skipped unsupported provider maps to blocked receipt/bridge."""
    from scripts.bench.h5_cloud_fallback_e2e_smoke import run_h5_cloud_fallback_e2e_smoke

    result = run_h5_cloud_fallback_e2e_smoke(provider="unknown", dry_run=True)

    assert result["evidence_bundle"]["bundle_status"] == "blocked"
    assert result["ingestion_validation"]["validation_status"] == "rejected"


def test_h5_22_synthetic_ready_smoke_maps_to_pass_bundle():
    """H5-22 Test 3: synthetic ready smoke maps to pass bundle."""
    from scripts.bench.h5_cloud_fallback_e2e_smoke import build_h5_cloud_fallback_smoke_evidence_bundle

    smoke = {
        "status": "pass", "provider": "gemini", "dry_run": False,
        "cloud_fallback_would_invoke": True, "cloud_fallback_invoked": True,
        "cloud_model_invoked": True, "cloud_output_captured": True,
        "cloud_output_verified": True, "model_calls_before": 1,
        "model_calls_after_shadow": 2, "model_calls_incremented": False,
    }
    from scripts.bench.h5_cloud_fallback_e2e_smoke import build_h5_cloud_fallback_smoke_receipt, build_h5_cloud_fallback_readiness_bridge
    smoke["receipt"] = build_h5_cloud_fallback_smoke_receipt(smoke)
    smoke["readiness_bridge"] = build_h5_cloud_fallback_readiness_bridge(smoke["receipt"])
    bundle = build_h5_cloud_fallback_smoke_evidence_bundle(smoke)
    assert bundle["bundle_status"] == "pass"
    assert bundle["can_feed_h5_readiness_shadow"] is True


def test_h5_22_synthetic_pass_bundle_accepted_by_validation():
    """H5-22 Test 4: synthetic pass bundle accepted by validation."""
    from scripts.bench.h5_cloud_fallback_e2e_smoke import validate_h5_cloud_fallback_evidence_bundle

    bundle = {
        "schema": "nexus.h5_cloud_fallback_smoke_evidence_bundle.v1",
        "bundle_status": "pass",
        "can_feed_h5_readiness_shadow": True,
        "safety": {"final_source_changed": False, "final_patch_replaced": False,
                   "output_mutated": False, "model_calls_incremented": False,
                   "public_claim_allowed": False, "production_ready": False},
        "governance": {"public_claim_allowed": False, "production_ready": False, "internal_only": True},
        "receipt": {"schema": "nexus.h5_cloud_fallback_smoke_receipt.v1",
                     "h5_cloud_fallback_compatible": True, "h5_cloud_fallback_ready_shadow": True},
        "readiness_bridge": {"schema": "nexus.h5_cloud_fallback_readiness_bridge.v1",
                             "readiness_status": "ready_shadow",
                             "cloud_fallback_e2e_ready_shadow": True,
                             "can_feed_h5_readiness_shadow": True,
                             "provider_ready": True, "cloud_invocation_ready": True,
                             "cloud_output_capture_ready": True, "cloud_output_verification_ready": True,
                             "model_call_accounting_ready": True},
    }
    val = validate_h5_cloud_fallback_evidence_bundle(bundle)
    assert val["validation_status"] == "accepted"
    assert val["accepted_for_h5_readiness_shadow"] is True


def test_h5_22_invalid_bundle_schema_rejected():
    """H5-22 Test 5: invalid bundle schema rejected."""
    from scripts.bench.h5_cloud_fallback_e2e_smoke import validate_h5_cloud_fallback_evidence_bundle
    val = validate_h5_cloud_fallback_evidence_bundle({"schema": "wrong"})
    assert val["validation_status"] == "rejected"
    assert "invalid_bundle_schema" in val["validation_reasons"]


def test_h5_22_safety_violation_rejected():
    """H5-22 Test 6: safety invariant violation rejected."""
    from scripts.bench.h5_cloud_fallback_e2e_smoke import validate_h5_cloud_fallback_evidence_bundle
    bundle = {"schema": "nexus.h5_cloud_fallback_smoke_evidence_bundle.v1",
              "safety": {"output_mutated": True}}
    val = validate_h5_cloud_fallback_evidence_bundle(bundle)
    assert val["validation_status"] == "rejected"
    assert "safety_invariant_violation" in val["validation_reasons"]


def test_h5_22_governance_violation_rejected():
    """H5-22 Test 7: governance violation rejected."""
    from scripts.bench.h5_cloud_fallback_e2e_smoke import validate_h5_cloud_fallback_evidence_bundle
    bundle = {"schema": "nexus.h5_cloud_fallback_smoke_evidence_bundle.v1",
              "governance": {"production_ready": True}}
    val = validate_h5_cloud_fallback_evidence_bundle(bundle)
    assert val["validation_status"] == "rejected"
    assert "governance_boundary_violation" in val["validation_reasons"]


def test_h5_22_receipt_incompatible_rejected():
    """H5-22 Test 8: receipt incompatible rejected."""
    from scripts.bench.h5_cloud_fallback_e2e_smoke import validate_h5_cloud_fallback_evidence_bundle
    bundle = {"schema": "nexus.h5_cloud_fallback_smoke_evidence_bundle.v1",
              "receipt": {"schema": "nexus.h5_cloud_fallback_smoke_receipt.v1",
                          "h5_cloud_fallback_compatible": False}}
    val = validate_h5_cloud_fallback_evidence_bundle(bundle)
    assert val["validation_status"] == "rejected"
    assert "receipt_not_h5_cloud_fallback_compatible" in val["validation_reasons"]


def test_h5_22_readiness_bridge_not_ready_rejected():
    """H5-22 Test 9: readiness bridge not ready rejected."""
    from scripts.bench.h5_cloud_fallback_e2e_smoke import validate_h5_cloud_fallback_evidence_bundle
    bundle = {"schema": "nexus.h5_cloud_fallback_smoke_evidence_bundle.v1",
              "readiness_bridge": {"schema": "nexus.h5_cloud_fallback_readiness_bridge.v1",
                                   "readiness_status": "blocked"}}
    val = validate_h5_cloud_fallback_evidence_bundle(bundle)
    assert val["validation_status"] == "rejected"
    assert "readiness_bridge_not_ready" in val["validation_reasons"]


def test_h5_22_cli_dry_run_includes_bundle_and_validation():
    """H5-22 Test 10: CLI dry-run includes evidence_bundle and ingestion_validation."""
    script = Path(__file__).resolve().parents[2] / "scripts" / "bench" / "h5_cloud_fallback_e2e_smoke.py"
    result = subprocess.run(
        [sys.executable, str(script), "--dry-run", "--provider", "gemini"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert "evidence_bundle" in data
    assert "ingestion_validation" in data
