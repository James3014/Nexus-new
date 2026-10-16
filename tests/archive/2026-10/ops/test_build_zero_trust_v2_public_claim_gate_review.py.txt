from __future__ import annotations

from scripts.ops.build_zero_trust_v2_public_claim_gate_review import (
    build_zero_trust_v2_public_claim_gate_review,
)


def _runtime_ready() -> dict:
    return {
        "status": "PASS",
        "summary": {"runtime_update_allowed": True, "v2_default_applied_count": 34},
    }


def _behavior_ready() -> dict:
    return {"status": "PASS", "summary": {"v2_behavior_ready_count": 34}}


def _unified_ready() -> dict:
    return {"status": "PASS", "summary": {"v2_unification_complete": True}}


def _bundle(tmp_path, *, verdict="PASS", failures=None, checks=None):
    root = tmp_path / "zero_trust_v2_behavior" / "cap" / "skill" / "run-01"
    root.mkdir(parents=True)
    payload = {
        "schema": "nexus_public_benchmark_evidence_bundle_v2",
        "public_claim_gate": {
            "verdict": verdict,
            "failures": failures or [],
            "checks": {
                "same_model": True,
                "same_task_trials": True,
                "hidden_verifier_mode": True,
                "run_eligibility_complete": True,
                "valid_comparison_ready": True,
                "eligible_with_nexus": 1,
                "eligible_without_nexus": 1,
                "infra_valid_pair_count": 1,
                "token_measured_rate_with": 1.0,
                "token_measured_rate_without": 1.0,
                "provider_token_measured_rate_with": 1.0,
                "provider_token_measured_rate_without": 1.0,
                "raw_file_hashes_present": True,
                "runner_command_present": True,
                "manifest_hash_present": True,
                "nexus_wearing_valid_rate": 1.0,
                **(checks or {}),
            },
        },
        "public_verified_delivery_claim_gate": {"verdict": "PASS", "failures": []},
        "public_cost_claim_gate": {"verdict": "PASS", "failures": []},
        "public_cost_efficiency_claim_gate": {"verdict": "IMPROVED", "failures": []},
        "x3_promotion_gate": {"verdict": "PASS", "failures": []},
        "external_provider_claim_boundary_contract": {"public_claim_allowed": True},
        "public_promotion_readiness_contract": {"status": "PASS"},
        "public_lane_contract": {"non_public_reasons": []},
    }
    (root / "evidence_bundle.json").write_text(__import__("json").dumps(payload), encoding="utf-8")
    return tmp_path / "zero_trust_v2_behavior"


def test_public_claim_gate_review_can_pass_when_public_bundle_and_runtime_are_clean(tmp_path):
    evidence_root = _bundle(tmp_path)

    result = build_zero_trust_v2_public_claim_gate_review(
        behavior_evidence=_behavior_ready(),
        runtime_status=_runtime_ready(),
        unified_mainline=_unified_ready(),
        evidence_root=evidence_root,
    )

    assert result["status"] == "PASS"
    assert result["summary"]["public_benchmark_allowed"] is True
    assert result["blockers"] == []
    assert result["summary"]["public_cost_efficiency_claim_gate_improved_count"] == 1
    assert result["claim_scope"]["profile"] == "NEXUS_ALLOW_COST_EFFICIENCY_PRE_MODEL_RESCUE=1"


def test_public_claim_gate_review_blocks_nexus_only_single_arm_evidence(tmp_path):
    evidence_root = _bundle(
        tmp_path,
        verdict="FAIL",
        failures=[
            "non_public_shortcut:nexus_only",
            "single_arm_run",
            "without_provider_token_measured_below_threshold",
        ],
        checks={
            "same_model": False,
            "same_task_trials": False,
            "valid_comparison_ready": False,
            "eligible_without_nexus": 0,
            "infra_valid_pair_count": 0,
            "token_measured_rate_without": 0.0,
            "provider_token_measured_rate_without": 0.0,
        },
    )

    result = build_zero_trust_v2_public_claim_gate_review(
        behavior_evidence=_behavior_ready(),
        runtime_status=_runtime_ready(),
        unified_mainline=_unified_ready(),
        evidence_root=evidence_root,
    )

    assert result["status"] == "BLOCKED"
    assert result["summary"]["public_benchmark_allowed"] is False
    assert "no_public_claim_gate_pass" in result["blockers"]
    assert "nexus_only_shortcut_evidence_present" in result["blockers"]
    assert "baseline_provider_token_cost_accounting_missing" in result["blockers"]


def test_public_claim_gate_review_can_select_single_final_evidence_bundle(tmp_path):
    evidence_root = _bundle(tmp_path)
    evidence_bundle = next(evidence_root.glob("**/evidence_bundle.json"))

    result = build_zero_trust_v2_public_claim_gate_review(
        behavior_evidence=_behavior_ready(),
        runtime_status=_runtime_ready(),
        unified_mainline=_unified_ready(),
        evidence_root=tmp_path / "missing_old_behavior_root",
        evidence_bundle=evidence_bundle,
    )

    assert result["status"] == "PASS"
    assert result["evidence_selection"] == {
        "mode": "single_final_evidence_bundle",
        "evidence_bundle": evidence_bundle.as_posix(),
        "evidence_root": "",
    }
    assert result["summary"]["evidence_bundle_count"] == 1
    assert result["summary"]["x3_promotion_gate_pass_count"] == 1


def test_public_claim_gate_review_blocks_when_runtime_default_not_ready(tmp_path):
    evidence_root = _bundle(tmp_path)

    result = build_zero_trust_v2_public_claim_gate_review(
        behavior_evidence=_behavior_ready(),
        runtime_status={"status": "PASS", "summary": {"runtime_update_allowed": False, "v2_default_applied_count": 0}},
        unified_mainline=_unified_ready(),
        evidence_root=evidence_root,
    )

    assert result["status"] == "BLOCKED"
    assert result["blockers"] == ["runtime_default_not_applied", "v2_default_applied_count_lt_34"]


def test_public_claim_gate_review_blocks_without_evidence_bundles(tmp_path):
    result = build_zero_trust_v2_public_claim_gate_review(
        behavior_evidence=_behavior_ready(),
        runtime_status=_runtime_ready(),
        unified_mainline=_unified_ready(),
        evidence_root=tmp_path / "missing",
    )

    assert result["status"] == "BLOCKED"
    assert result["blockers"] == ["zero_trust_v2_public_evidence_bundles_missing"]
