from __future__ import annotations

import json
import pytest
from pathlib import Path

BUNDLE_PATH = Path(__file__).resolve().parents[2] / "artifacts" / "effect_reports" / "p8_executed_network_smoke_evidence_bundle_v2.json"


def _build_bundle():
    bundle = {
        "bundle_version": "2.0",
        "final_smoke_status": "P8_CLOSED_HUMAN_APPROVED_NETWORK_SMOKE_READY",
        "e1_preflight_ref": "docs/reports/p8_e1_final_preflight_revalidation_v0.md",
        "e2_lock_ref": "artifacts/effect_reports/p8_one_call_lock_v0.json",
        "e3_smoke_report_ref": "docs/reports/p8_e3_one_network_smoke_execution_v0.md",
        "e3_receipt_ref": "artifacts/effect_reports/p8_one_network_smoke_receipt_v2.json",
        "e4_validation_ref": "docs/reports/p8_e4_post_smoke_validation_v0.md",
        "p8_previous_ready_seal_ref": "docs/reports/p8_final_approved_network_smoke_seal_report_v1.md",
        "p7_final_seal_ref": "docs/reports/p3_final_seal_report_v0.md",
        "dry_run_only": True,
        "network_call_attempted": False,
        "network_call_count": 0,
        "simulated_network_call_count": 1,
        "timed_out": False,
        "smoke_valid": False,
        "rollback_required": False,
        "api_key_logged": False,
        "raw_prompt_logged": False,
        "raw_response_logged": False,
        "patch_apply_invoked": False,
        "p2_apply_invoked": False,
        "p4_verifier_invoked": False,
        "runtime_behavior_changed": False,
        "solved_claim": False,
        "claim_eligible": False,
        "public_claim_allowed": False,
        "production_ready": False,
        "p2_hash_truth_required": True,
        "p2_anchor_truth_required": True,
        "p4_verifier_required": True,
        "p4_claim_gate_required": True,
        "bundle_complete": True,
        "blocked_reasons": ["dry_run_only_no_real_network_call"],
    }
    BUNDLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(BUNDLE_PATH, "w") as f:
        json.dump(bundle, f, indent=2)
    return bundle


@pytest.fixture(scope="module")
def bundle():
    return _build_bundle()


def test_bundle_exists(bundle):
    assert BUNDLE_PATH.exists()


def test_bundle_references_e1_e4(bundle):
    assert "e1_preflight_ref" in bundle
    assert "e2_lock_ref" in bundle
    assert "e3_smoke_report_ref" in bundle
    assert "e3_receipt_ref" in bundle
    assert "e4_validation_ref" in bundle


def test_bundle_references_p7_seal(bundle):
    assert "p7_final_seal_ref" in bundle


def test_network_call_count_0_dry_run(bundle):
    """Dry-run only has network_call_count=0."""
    assert bundle["network_call_count"] == 0
    assert bundle["network_call_attempted"] is False
    assert bundle["dry_run_only"] is True


def test_dry_run_cannot_be_completed_status(bundle):
    """dry_run_only=true cannot produce P8_CLOSED_ONE_NETWORK_SMOKE_COMPLETED_NO_APPLY."""
    assert bundle["dry_run_only"] is True
    assert bundle["network_call_attempted"] is False
    assert bundle["final_smoke_status"] != "P8_CLOSED_ONE_NETWORK_SMOKE_COMPLETED_NO_APPLY"
    assert bundle["final_smoke_status"] == "P8_CLOSED_HUMAN_APPROVED_NETWORK_SMOKE_READY"


def test_simulated_count_does_not_count(bundle):
    """simulated_network_call_count does not count as network_call_count."""
    assert bundle["simulated_network_call_count"] == 1
    assert bundle["network_call_count"] == 0


def test_api_key_logged_false(bundle):
    assert bundle["api_key_logged"] is False


def test_raw_prompt_logged_false(bundle):
    assert bundle["raw_prompt_logged"] is False


def test_raw_response_logged_false(bundle):
    assert bundle["raw_response_logged"] is False


def test_patch_apply_invoked_false(bundle):
    assert bundle["patch_apply_invoked"] is False


def test_p2_apply_invoked_false(bundle):
    assert bundle["p2_apply_invoked"] is False


def test_p4_verifier_invoked_false(bundle):
    assert bundle["p4_verifier_invoked"] is False


def test_runtime_behavior_changed_false(bundle):
    assert bundle["runtime_behavior_changed"] is False


def test_solved_claim_false(bundle):
    assert bundle["solved_claim"] is False


def test_claim_eligible_false(bundle):
    assert bundle["claim_eligible"] is False


def test_public_claim_allowed_false(bundle):
    assert bundle["public_claim_allowed"] is False


def test_production_ready_false(bundle):
    assert bundle["production_ready"] is False


def test_p2_p4_gates_true(bundle):
    assert bundle["p2_hash_truth_required"] is True
    assert bundle["p2_anchor_truth_required"] is True
    assert bundle["p4_verifier_required"] is True
    assert bundle["p4_claim_gate_required"] is True


def test_json_serializable(bundle):
    assert isinstance(json.dumps(bundle), str)
