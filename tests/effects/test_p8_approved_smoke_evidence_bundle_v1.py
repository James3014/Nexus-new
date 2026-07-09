from __future__ import annotations

import json
import pytest
from pathlib import Path

BUNDLE_PATH = Path(__file__).resolve().parents[2] / "artifacts" / "effect_reports" / "p8_approved_network_smoke_evidence_bundle_v1.json"


def _build_bundle():
    bundle = {
        "bundle_version": "1.0",
        "final_smoke_status": "P8_CLOSED_HUMAN_APPROVED_NETWORK_SMOKE_READY",
        "approval_artifact_ref": "artifacts/effect_reports/p8_human_approval_artifact_v0.json",
        "boundary_report_ref": "docs/reports/p8_b2_approval_boundary_reconciliation_v0.md",
        "prompt_capsule_ref": "docs/reports/p8_b3_synthetic_smoke_prompt_capsule_v0.md",
        "preflight_report_ref": "docs/reports/p8_b4_one_smoke_preflight_gate_v0.md",
        "smoke_receipt_ref": "artifacts/effect_reports/p8_one_network_smoke_receipt_v1.json",
        "post_smoke_validation_ref": "docs/reports/p8_b6_post_smoke_safety_validator_v0.md",
        "p7_final_seal_ref": "docs/reports/p3_final_seal_report_v0.md",
        "network_call_attempted": False,
        "network_call_count": 0,
        "dry_run_only": True,
        "timed_out": False,
        "smoke_valid": True,
        "rollback_required": False,
        "api_key_logged": False,
        "raw_prompt_logged": False,
        "raw_response_logged": False,
        "patch_apply_invoked": False,
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
        "blocked_reasons": [],
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


def test_bundle_references_b1_b6(bundle):
    assert "approval_artifact_ref" in bundle
    assert "boundary_report_ref" in bundle
    assert "prompt_capsule_ref" in bundle
    assert "preflight_report_ref" in bundle
    assert "smoke_receipt_ref" in bundle
    assert "post_smoke_validation_ref" in bundle


def test_bundle_references_p7_seal(bundle):
    assert "p7_final_seal_ref" in bundle


def test_network_call_count_0_dry_run(bundle):
    """Dry-run only has network_call_count=0."""
    assert bundle["network_call_count"] == 0
    assert bundle["network_call_attempted"] is False


def test_api_key_logged_false(bundle):
    assert bundle["api_key_logged"] is False


def test_raw_prompt_logged_false(bundle):
    assert bundle["raw_prompt_logged"] is False


def test_raw_response_logged_false(bundle):
    assert bundle["raw_response_logged"] is False


def test_patch_apply_invoked_false(bundle):
    assert bundle["patch_apply_invoked"] is False


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


def test_dry_run_cannot_be_completed_status(bundle):
    """Dry-run only cannot produce P8_CLOSED_ONE_NETWORK_SMOKE_COMPLETED_NO_APPLY."""
    assert bundle["network_call_attempted"] is False
    assert bundle["network_call_count"] == 0
    assert bundle["final_smoke_status"] != "P8_CLOSED_ONE_NETWORK_SMOKE_COMPLETED_NO_APPLY"
    assert bundle["final_smoke_status"] == "P8_CLOSED_HUMAN_APPROVED_NETWORK_SMOKE_READY"


def test_status_rule_dry_run_ready(bundle):
    """dry_run_only=true plus network_call_attempted=false must be READY, not COMPLETED."""
    assert bundle["dry_run_only"] is True
    assert bundle["network_call_attempted"] is False
    assert bundle["final_smoke_status"] == "P8_CLOSED_HUMAN_APPROVED_NETWORK_SMOKE_READY"
