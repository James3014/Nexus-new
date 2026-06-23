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

    assert result["receipt"]["status"] == "skipped"
    assert result["readiness_bridge"]["readiness_status"] == "blocked"


def test_h5_21_synthetic_complete_real_smoke_maps_to_compatible_receipt():
    """H5-21 Test 3: synthetic complete real smoke maps to compatible receipt."""
    from scripts.bench.h5_cloud_fallback_e2e_smoke import build_h5_cloud_fallback_smoke_receipt

    smoke = {
        "status": "pass", "provider": "gemini", "dry_run": False,
        "cloud_fallback_would_invoke": True, "cloud_fallback_invoked": True,
        "cloud_model_invoked": True, "cloud_output_captured": True,
        "cloud_output_verified": True, "model_calls_before": 1,
        "model_calls_after_shadow": 2, "model_calls_incremented": False,
        "final_source_changed": False, "final_patch_replaced": False,
        "output_mutated": False,
    }
    receipt = build_h5_cloud_fallback_smoke_receipt(smoke)
    assert receipt["h5_cloud_fallback_compatible"] is True
    assert receipt["h5_cloud_fallback_ready_shadow"] is True


def test_h5_21_synthetic_complete_receipt_maps_to_ready_bridge():
    """H5-21 Test 4: synthetic complete receipt maps to ready bridge."""
    from scripts.bench.h5_cloud_fallback_e2e_smoke import build_h5_cloud_fallback_readiness_bridge

    receipt = {
        "status": "pass", "provider": "gemini", "dry_run": False,
        "h5_cloud_fallback_compatible": True,
        "cloud_fallback_invoked": True, "cloud_model_invoked": True,
        "cloud_output_captured": True, "cloud_output_verified": True,
        "model_calls_before": 1, "model_calls_after_shadow": 2,
        "model_calls_incremented": False,
    }
    bridge = build_h5_cloud_fallback_readiness_bridge(receipt)
    assert bridge["readiness_status"] == "ready_shadow"
    assert bridge["cloud_fallback_e2e_ready_shadow"] is True
    assert bridge["can_feed_h5_readiness_shadow"] is True
    assert bridge["provider_ready"] is True
    assert bridge["cloud_invocation_ready"] is True
    assert bridge["cloud_output_capture_ready"] is True
    assert bridge["cloud_output_verification_ready"] is True
    assert bridge["model_call_accounting_ready"] is True


def test_h5_21_missing_output_verification_blocks():
    """H5-21 Test 5: missing output verification blocks."""
    from scripts.bench.h5_cloud_fallback_e2e_smoke import build_h5_cloud_fallback_readiness_bridge

    receipt = {
        "status": "pass", "provider": "gemini", "dry_run": False,
        "h5_cloud_fallback_compatible": False,
        "h5_cloud_fallback_blocked_reason": "cloud_output_not_verified",
    }
    bridge = build_h5_cloud_fallback_readiness_bridge(receipt)
    assert bridge["cloud_output_verification_ready"] is False
    assert bridge["readiness_status"] == "blocked"


def test_h5_21_invalid_model_call_accounting_blocks():
    """H5-21 Test 6: invalid model call accounting blocks."""
    from scripts.bench.h5_cloud_fallback_e2e_smoke import build_h5_cloud_fallback_readiness_bridge

    receipt = {
        "status": "pass", "provider": "gemini", "dry_run": False,
        "h5_cloud_fallback_compatible": False,
        "model_calls_before": 1, "model_calls_after_shadow": 3,
        "model_calls_incremented": False,
    }
    bridge = build_h5_cloud_fallback_readiness_bridge(receipt)
    assert bridge["model_call_accounting_ready"] is False
    assert bridge["readiness_status"] == "blocked"


def test_h5_21_unexpected_model_calls_incremented_blocks():
    """H5-21 Test 7: unexpected model_calls_incremented blocks."""
    from scripts.bench.h5_cloud_fallback_e2e_smoke import build_h5_cloud_fallback_readiness_bridge

    receipt = {
        "status": "pass", "provider": "gemini", "dry_run": False,
        "h5_cloud_fallback_compatible": False,
        "model_calls_before": 1, "model_calls_after_shadow": 2,
        "model_calls_incremented": True,
    }
    bridge = build_h5_cloud_fallback_readiness_bridge(receipt)
    assert bridge["model_call_accounting_ready"] is False


def test_h5_21_safety_invariants_remain_false():
    """H5-21 Test 8: safety invariants remain false."""
    from scripts.bench.h5_cloud_fallback_e2e_smoke import build_h5_cloud_fallback_readiness_bridge

    bridges = [
        {},
        {"status": "skipped", "dry_run": True},
        {"status": "pass", "dry_run": False, "provider": "gemini",
         "h5_cloud_fallback_compatible": True, "cloud_fallback_invoked": True,
         "cloud_model_invoked": True, "cloud_output_captured": True,
         "cloud_output_verified": True, "model_calls_before": 1,
         "model_calls_after_shadow": 2, "model_calls_incremented": False},
    ]
    for b in bridges:
        bridge = build_h5_cloud_fallback_readiness_bridge(b)
        assert bridge["final_source_changed"] is False
        assert bridge["final_patch_replaced"] is False
        assert bridge["output_mutated"] is False
        assert bridge["model_calls_incremented"] is False
        assert bridge["public_claim_allowed"] is False
        assert bridge["production_ready"] is False


def test_h5_21_cli_dry_run_includes_receipt_and_bridge():
    """H5-21 Test 9: CLI dry-run includes receipt and readiness_bridge."""
    script = Path(__file__).resolve().parents[2] / "scripts" / "bench" / "h5_cloud_fallback_e2e_smoke.py"
    result = subprocess.run(
        [sys.executable, str(script), "--dry-run", "--provider", "gemini"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert "receipt" in data
    assert data["receipt"]["schema"] == "nexus.h5_cloud_fallback_smoke_receipt.v1"
    assert "readiness_bridge" in data
    assert data["readiness_bridge"]["schema"] == "nexus.h5_cloud_fallback_readiness_bridge.v1"
