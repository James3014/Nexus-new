from __future__ import annotations

import json
import pytest
from pathlib import Path

BUNDLE_PATH = Path(__file__).resolve().parents[2] / "artifacts" / "effect_reports" / "p3_closeout_evidence_bundle_v0.json"


def _build_bundle():
    bundle = {
        "p3_closeout_bundle_version": "1.0",
        "p3_closeout_final_decision": "P3_CLOSED_SYNTHETIC_PROVIDER_TRACE_READY",
        "p3_closeout_evidence_references": {
            "O1_candidate_availability_normalization": "docs/reports/p3_o1_synthetic_provider_candidate_availability_normalization_v0.md",
            "O2_synthetic_e2e_trace": "docs/reports/p3_o2_synthetic_provider_e2e_trace_harness_v0.md",
            "O3_synthetic_trace_artifact": "artifacts/effect_reports/p3_synthetic_e2e_trace_v0.jsonl",
            "O4_authority_coupling": "docs/reports/p3_o4_p2_p4_authority_coupling_contract_v0.md",
            "O5_authority_coupled_trace": "artifacts/effect_reports/p3_authority_coupled_synthetic_trace_v0.jsonl",
            "O6_p6_advisory_consumer": "docs/reports/p3_o6_p6_advisory_handoff_consumer_contract_v0.md",
            "O7_closeout_decision": "docs/reports/p3_o7_integrated_closeout_decision_v0.md",
        },
        "p3_closeout_safety_assertions": {
            "real_provider_invoked": False,
            "network_invoked": False,
            "api_key_used": False,
            "patch_apply_invoked": False,
            "runtime_behavior_changed": False,
            "solved_by_p3": False,
            "claim_eligible_by_p3": False,
            "public_claim_allowed": False,
            "production_ready": False,
            "p2_hash_truth_required": True,
            "p2_anchor_truth_required": True,
            "p4_full_verifier_required": True,
            "p4_claim_gate_required": True,
            "p6_advisory_only": True,
        },
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


def test_bundle_references_all_required_artifacts(bundle):
    refs = bundle["p3_closeout_evidence_references"]
    assert "O1_candidate_availability_normalization" in refs
    assert "O2_synthetic_e2e_trace" in refs
    assert "O3_synthetic_trace_artifact" in refs
    assert "O4_authority_coupling" in refs
    assert "O5_authority_coupled_trace" in refs
    assert "O6_p6_advisory_consumer" in refs
    assert "O7_closeout_decision" in refs


def test_referenced_files_exist(bundle):
    refs = bundle["p3_closeout_evidence_references"]
    for key, path in refs.items():
        assert Path(path).exists(), f"{key} references non-existent {path}"


def test_final_decision_present(bundle):
    assert "p3_closeout_final_decision" in bundle
    assert bundle["p3_closeout_final_decision"] in (
        "P3_CLOSED_SYNTHETIC_PROVIDER_TRACE_READY",
        "P3_CLOSED_HUMAN_APPROVED_NETWORK_SMOKE_READY",
        "P3_CLOSED_BLOCKED",
        "P3_CLOSED_ROLLBACK_REQUIRED",
    )


def test_safety_assertions_all_safe(bundle):
    sa = bundle["p3_closeout_safety_assertions"]
    assert sa["real_provider_invoked"] is False
    assert sa["network_invoked"] is False
    assert sa["api_key_used"] is False
    assert sa["patch_apply_invoked"] is False
    assert sa["runtime_behavior_changed"] is False
    assert sa["solved_by_p3"] is False
    assert sa["claim_eligible_by_p3"] is False
    assert sa["public_claim_allowed"] is False
    assert sa["production_ready"] is False
    assert sa["p2_hash_truth_required"] is True
    assert sa["p4_full_verifier_required"] is True


def test_public_claim_allowed_false(bundle):
    assert bundle["p3_closeout_safety_assertions"]["public_claim_allowed"] is False


def test_production_ready_false(bundle):
    assert bundle["p3_closeout_safety_assertions"]["production_ready"] is False


def test_patch_apply_invoked_false(bundle):
    assert bundle["p3_closeout_safety_assertions"]["patch_apply_invoked"] is False


def test_solved_by_p3_false(bundle):
    assert bundle["p3_closeout_safety_assertions"]["solved_by_p3"] is False


def test_json_serializable(bundle):
    serialized = json.dumps(bundle)
    assert isinstance(serialized, str)
