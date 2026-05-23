from __future__ import annotations

from pathlib import Path

from scripts.bench.evidence_bundle_posture import (
    append_x1_readiness_history,
    derive_direction_magnitude_gate,
    derive_public_claim_posture,
    derive_recent_compatible_x1_history,
    derive_training_eligibility_posture,
    derive_x3_promotion_gate,
    load_x1_readiness_history,
    x1_readiness_history_path,
)


def test_claim_and_training_posture_keep_public_boundaries():
    claim = derive_public_claim_posture(
        delivery_gate_passed=True,
        cost_claim_passed=True,
        cost_efficiency_status="IMPROVED",
        cost_efficiency_failures=[],
        cost_efficiency_sample_sufficient=False,
        efficiency_pair_count=1,
        min_required_pairs_for_efficiency_claim=3,
        token_roi_status="EFFICIENT",
        verified_lift_per_1k_with_tokens=0.2,
        marginal_token_utility=0.1,
        retry_cost_share_wall=0.0,
    )
    training = derive_training_eligibility_posture(
        delivery_gate_passed=False,
        cost_claim_passed=False,
        cost_efficiency_sample_sufficient=True,
        prompt_purity_gate_passed=True,
        with_trust_mismatch_rate=0.0,
        without_trust_mismatch_rate=0.0,
        eligible_with=[{"rubric_contract_status": "PASS"}],
        infra_quarantine_report={"infra_valid_pair_count": 3, "infra_invalid_pair_count": 0},
        cost_efficiency_status="IMPROVED",
        synthetic_readiness_reasons=["force_learn_slo_ready"],
    )

    assert claim["public_wording_key"] == "promising_but_insufficient_sample"
    assert claim["cost_efficiency_wording_allowed"] is False
    assert training["status"] == "OBSERVATION_ONLY_SYNTHETIC_READINESS"
    assert "synthetic_readiness_shortcut:force_learn_slo_ready" in training["reason_codes"]


def test_direction_and_x3_gates_are_fail_closed_until_history_is_clean():
    direction = derive_direction_magnitude_gate(
        valid_comparison_ready=True,
        wall_cost_ratio_with_over_without=0.98,
        token_cost_ratio_with_over_without=0.97,
        model_call_ratio_with_over_without=1.0,
        paired_wall_ratios=[0.98, 1.01],
        paired_token_ratios=[0.97, 1.0],
    )
    x3 = derive_x3_promotion_gate(
        history_last_two_x1_readiness_pass=["false", True],
        valid_comparison_ready=True,
        wall_ledger_with_conserved_rate=1.0,
        wall_ledger_without_conserved_rate=1.0,
        warning_clean_gate_pass=True,
        provider_token_measured_rate_with=1.0,
        provider_token_measured_rate_without=1.0,
    )

    assert direction["status"] == "NEUTRAL"
    assert "improvement_below_5pct" in direction["failures"]
    assert x3["status"] == "RETURN"
    assert x3["checks"]["history_last_two_x1_readiness_pass"] == [False, True]


def test_x1_history_helpers_filter_and_cap_entries(tmp_path: Path):
    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text("{broken", encoding="utf-8")
    assert load_x1_readiness_history(corrupt) == []

    history_path = tmp_path / "x1_readiness_history.json"
    append_x1_readiness_history(
        path=history_path,
        entry={"model": "m1", "tasks_manifest_hash": "h1", "x1_readiness_pass": False, "timestamp": 1},
        max_entries=2,
    )
    append_x1_readiness_history(
        path=history_path,
        entry={"model": "m2", "tasks_manifest_hash": "h1", "x1_readiness_pass": True, "timestamp": 2},
        max_entries=2,
    )
    history = append_x1_readiness_history(
        path=history_path,
        entry={"model": "m1", "tasks_manifest_hash": "h1", "x1_readiness_pass": True, "timestamp": 3},
        max_entries=2,
    )

    assert [item["timestamp"] for item in history] == [2, 3]
    assert derive_recent_compatible_x1_history(
        x1_history=history,
        model_label="m1",
        manifest_hash="h1",
    ) == [True]
    assert x1_readiness_history_path(
        bundle_path=tmp_path / "run" / "evidence_bundle.json",
        config={"repo_root": str(tmp_path)},
    ) == tmp_path / ".nexus" / "reports" / "learn" / "x1_readiness_history.json"
