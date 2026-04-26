from scripts.bench.capability_s_grade import evaluate_s_grade


def _full_ab_payload(
    weighted: float = 0.98,
    daily_solve: float = 1.0,
    daily_semantic: float = 1.0,
    hard_delta: float = 1.0,
    cross_delta: float = 1.0,
    flash_file_task: bool = False,
    flash_model_calls: float = 1.0,
    realism_score: float | None = None,
    flash_wall_overhead: float = 45.0,
) -> dict:
    payload = {
        "weighted_score": weighted,
        "buckets": [
            {
                "name": "daily",
                "kpi": {
                    "with_solve_rate": daily_solve,
                    "with_semantic_verified_rate": daily_semantic,
                    "with_trust_mismatch_rate": 0.0,
                },
            },
            {
                "name": "hard",
                "kpi": {
                    "delta_solve_rate": hard_delta,
                    "with_semantic_verified_rate": 1.0,
                    "with_trust_mismatch_rate": 0.0,
                },
            },
            {
                "name": "cross_module",
                "kpi": {
                    "delta_solve_rate": cross_delta,
                    "with_semantic_verified_rate": 1.0,
                    "with_trust_mismatch_rate": 0.0,
                },
            },
            {
                "name": "cross_module_stress",
                "kpi": {
                    "delta_solve_rate": cross_delta,
                    "with_trust_mismatch_rate": 0.0,
                },
            },
        ],
    }
    if realism_score is not None:
        payload["realism_score"] = realism_score
    if flash_file_task:
        payload["buckets"].append(
            {
                "name": "flash_file_task_cross_module",
                "kpi": {
                    "with_solve_rate": 1.0,
                    "with_semantic_verified_rate": 1.0,
                    "with_trust_mismatch_rate": 0.0,
                    "with_avg_model_calls": flash_model_calls,
                    "with_token_measured_rate": 1.0,
                    "wall_overhead_sec": flash_wall_overhead,
                },
                "ab_eval": {
                    "b": {
                        "summary": {
                            "avg_model_calls": flash_model_calls,
                            "token_measured_rate": 1.0,
                            "avg_total_tokens": 1000.0,
                        }
                    }
                },
            }
        )
    return payload


def _ops_payload(
    overhead: float = 1.1,
    overhead_p95: float | None = None,
    overhead_worst_decile: float | None = None,
    solve_rate: float = 1.0,
    semantic_rate: float = 1.0,
    first_pass: float = 0.9,
    repair_success: float = 1.0,
    learn_attempt: float = 0.9,
    learn_citation: float = 0.8,
    semantic_contract_verified: float = 1.0,
    rolling_pass: bool = True,
    rolling_pass_count: int = 6,
    rolling14_pass: bool = False,
    rolling14_pass_count: int = 0,
) -> dict:
    p95 = overhead if overhead_p95 is None else overhead_p95
    worst_decile = overhead if overhead_worst_decile is None else overhead_worst_decile
    return {
        "trend_gate": {"verdict": "PASS"},
        "stability_rolling_7": {
            "window": 7,
            "required_passes": 6,
            "available_rounds": 7,
            "pass_count": rolling_pass_count,
            "pass": rolling_pass,
        },
        "stability_rolling_14": {
            "window": 14,
            "required_passes": 13,
            "available_rounds": 14,
            "pass_count": rolling14_pass_count,
            "pass": rolling14_pass,
        },
        "kpi_median_3round": {
            "with_solve_rate": solve_rate,
            "with_semantic_verified_rate": semantic_rate,
            "wall_overhead_sec": overhead,
            "wall_overhead_p95_sec": p95,
            "wall_overhead_worst_decile_mean_sec": worst_decile,
        },
        "self_heal": {
            "first_pass_success_rate": first_pass,
            "repair_success_rate": repair_success,
        },
        "capability_paths": {
            "learn_mode_attempt_rate": learn_attempt,
            "learn_mode_citation_usage_rate": learn_citation,
        },
        "anti_hallucination": {
            "semantic_contract_verified_rate": semantic_contract_verified,
        },
    }


def test_evaluate_s_grade_passes_when_all_rules_met():
    out = evaluate_s_grade(full_ab=_full_ab_payload(), ops_rounds=_ops_payload())
    assert out["summary"]["verdict"] == "S_PASS"
    assert out["summary"]["legacy_verdict"] == "S_PASS"
    assert out["summary"]["pass_ratio"] == 1.0
    assert out["summary"]["s_plus_pass_ratio"] < 1.0


def test_evaluate_s_grade_reaches_s_plus_when_stricter_targets_met():
    out = evaluate_s_grade(
        full_ab=_full_ab_payload(weighted=0.995, hard_delta=0.9, cross_delta=0.9),
        ops_rounds=_ops_payload(
            overhead=0.95,
            solve_rate=0.99,
            semantic_rate=0.99,
            first_pass=0.92,
            repair_success=0.95,
            learn_attempt=0.98,
            learn_citation=0.9,
            semantic_contract_verified=1.0,
        ),
    )
    assert out["summary"]["verdict"] == "S_PLUS"
    assert out["summary"]["legacy_verdict"] == "S_PLUS"
    assert out["summary"]["s_plus_pass_ratio"] == 1.0
    assert out["summary"]["s2_pass_ratio"] < 1.0


def test_evaluate_s_grade_reaches_s2_when_elite_targets_met():
    out = evaluate_s_grade(
        full_ab=_full_ab_payload(weighted=0.999, hard_delta=0.95, cross_delta=0.95),
        ops_rounds=_ops_payload(
            overhead=0.8,
            solve_rate=1.0,
            semantic_rate=1.0,
            first_pass=0.97,
            repair_success=1.0,
            learn_attempt=0.9,
            learn_citation=0.9,
            semantic_contract_verified=1.0,
        ),
    )
    assert out["summary"]["verdict"] == "S2_PASS"
    assert out["summary"]["legacy_verdict"] == "S2_PASS"
    assert out["summary"]["s2_pass_ratio"] == 1.0
    assert out["summary"]["s_elite_pass_ratio"] < 1.0


def test_evaluate_s_grade_reaches_s_elite_when_ultra_targets_met():
    out = evaluate_s_grade(
        full_ab=_full_ab_payload(weighted=1.0, hard_delta=1.0, cross_delta=1.0),
        ops_rounds=_ops_payload(
            overhead=0.7,
            solve_rate=1.0,
            semantic_rate=1.0,
            first_pass=1.0,
            repair_success=1.0,
            learn_attempt=1.0,
            learn_citation=1.0,
            semantic_contract_verified=1.0,
        ),
    )
    assert out["summary"]["verdict"] == "S_ELITE"
    assert out["summary"]["s_elite_pass_ratio"] == 1.0
    assert out["summary"]["s3_pass_ratio"] < 1.0


def test_evaluate_s_grade_reaches_s3_when_new_thresholds_met():
    out = evaluate_s_grade(
        full_ab=_full_ab_payload(weighted=1.0, hard_delta=1.0, cross_delta=1.0),
        ops_rounds=_ops_payload(
            overhead=0.6,
            overhead_p95=0.62,
            overhead_worst_decile=0.64,
            solve_rate=1.0,
            semantic_rate=1.0,
            first_pass=1.0,
            repair_success=1.0,
            learn_attempt=1.0,
            learn_citation=1.0,
            semantic_contract_verified=1.0,
        ),
    )
    assert out["summary"]["verdict"] == "S3_PASS"
    assert out["summary"]["legacy_verdict"] == "S3_PASS"
    assert out["summary"]["s3_pass_ratio"] == 1.0
    assert out["summary"]["s4_pass_ratio"] < 1.0


def test_evaluate_s_grade_reaches_s4_when_stricter_thresholds_met():
    out = evaluate_s_grade(
        full_ab=_full_ab_payload(weighted=1.0, hard_delta=1.0, cross_delta=1.0),
        ops_rounds=_ops_payload(
            overhead=0.5,
            overhead_p95=0.52,
            overhead_worst_decile=0.54,
            solve_rate=1.0,
            semantic_rate=1.0,
            first_pass=1.0,
            repair_success=1.0,
            learn_attempt=1.0,
            learn_citation=1.0,
            semantic_contract_verified=1.0,
        ),
    )
    assert out["summary"]["verdict"] == "S4_PASS"
    assert out["summary"]["legacy_verdict"] == "S4_PASS"
    assert out["summary"]["s4_pass_ratio"] == 1.0
    assert out["summary"]["s5_pass_ratio"] < 1.0


def test_evaluate_s_grade_reaches_s5_when_extreme_thresholds_met():
    out = evaluate_s_grade(
        full_ab=_full_ab_payload(weighted=1.0, hard_delta=1.0, cross_delta=1.0),
        ops_rounds=_ops_payload(
            overhead=0.4,
            overhead_p95=0.42,
            overhead_worst_decile=0.44,
            solve_rate=1.0,
            semantic_rate=1.0,
            first_pass=1.0,
            repair_success=1.0,
            learn_attempt=1.0,
            learn_citation=1.0,
            semantic_contract_verified=1.0,
        ),
    )
    assert out["summary"]["verdict"] == "S5_PASS"
    assert out["summary"]["legacy_verdict"] == "S5_PASS"
    assert out["summary"]["s5_pass_ratio"] == 1.0


def test_evaluate_s_grade_warns_when_core_signals_drop():
    out = evaluate_s_grade(
        full_ab=_full_ab_payload(weighted=0.8, daily_solve=0.7, daily_semantic=0.7),
        ops_rounds=_ops_payload(overhead=2.0),
    )
    assert out["summary"]["verdict"] in {"WARN", "B_PASS"}
    assert out["checks"]["full_ab_weighted_score"] is False
    assert out["checks"]["ops_overhead"] is False


def test_evaluate_s_grade_blocks_s3_when_stress_or_rolling_missing():
    out = evaluate_s_grade(
        full_ab=_full_ab_payload(weighted=1.0, hard_delta=1.0, cross_delta=1.0),
        ops_rounds=_ops_payload(
            overhead=0.55,
            overhead_p95=0.56,
            overhead_worst_decile=0.58,
            rolling_pass=False,
            rolling_pass_count=5,
            solve_rate=1.0,
            semantic_rate=1.0,
            first_pass=1.0,
            repair_success=1.0,
            learn_attempt=1.0,
            learn_citation=1.0,
            semantic_contract_verified=1.0,
        ),
    )
    assert out["summary"]["verdict"] != "S3_PASS"
    assert out["s3_checks"]["rolling_stability_7"] is False


def test_evaluate_s_grade_reaches_s6_when_rolling14_and_low_overhead_met():
    out = evaluate_s_grade(
        full_ab=_full_ab_payload(weighted=1.0, hard_delta=1.0, cross_delta=1.0),
        ops_rounds=_ops_payload(
            overhead=0.32,
            overhead_p95=0.39,
            overhead_worst_decile=0.49,
            solve_rate=1.0,
            semantic_rate=1.0,
            first_pass=1.0,
            repair_success=1.0,
            learn_attempt=1.0,
            learn_citation=1.0,
            semantic_contract_verified=1.0,
            rolling_pass=True,
            rolling_pass_count=7,
            rolling14_pass=True,
            rolling14_pass_count=14,
        ),
    )
    assert out["summary"]["verdict"] == "S6_PASS"
    assert out["summary"]["legacy_verdict"] == "S6_PASS"
    assert out["summary"]["s6_pass_ratio"] == 1.0


def test_evaluate_s_grade_reaches_s7_when_stricter_overhead_met():
    out = evaluate_s_grade(
        full_ab=_full_ab_payload(weighted=1.0, hard_delta=1.0, cross_delta=1.0),
        ops_rounds=_ops_payload(
            overhead=0.18,
            overhead_p95=0.24,
            overhead_worst_decile=0.29,
            solve_rate=1.0,
            semantic_rate=1.0,
            first_pass=1.0,
            repair_success=1.0,
            learn_attempt=1.0,
            learn_citation=1.0,
            semantic_contract_verified=1.0,
            rolling_pass=True,
            rolling_pass_count=7,
            rolling14_pass=True,
            rolling14_pass_count=14,
        ),
    )
    assert out["summary"]["verdict"] == "S7_PASS"
    assert out["summary"]["legacy_verdict"] == "S7_PASS"
    assert out["summary"]["s7_pass_ratio"] == 1.0


def test_evaluate_s_grade_blocks_s7_when_overhead_exceeds_new_ceiling():
    out = evaluate_s_grade(
        full_ab=_full_ab_payload(weighted=1.0, hard_delta=1.0, cross_delta=1.0),
        ops_rounds=_ops_payload(
            overhead=0.31,
            overhead_p95=0.31,
            overhead_worst_decile=0.29,
            solve_rate=1.0,
            semantic_rate=1.0,
            first_pass=1.0,
            repair_success=1.0,
            learn_attempt=1.0,
            learn_citation=1.0,
            semantic_contract_verified=1.0,
            rolling_pass=True,
            rolling_pass_count=7,
            rolling14_pass=True,
            rolling14_pass_count=14,
        ),
    )
    assert out["summary"]["verdict"] != "S7_PASS"
    assert out["s7_checks"]["ops_overhead"] is False


def test_evaluate_s_grade_reaches_s8_when_ultra_strict_targets_met():
    out = evaluate_s_grade(
        full_ab=_full_ab_payload(weighted=1.0, hard_delta=1.0, cross_delta=1.0),
        ops_rounds=_ops_payload(
            overhead=0.12,
            overhead_p95=0.19,
            overhead_worst_decile=0.24,
            solve_rate=1.0,
            semantic_rate=1.0,
            first_pass=1.0,
            repair_success=1.0,
            learn_attempt=1.0,
            learn_citation=1.0,
            semantic_contract_verified=1.0,
            rolling_pass=True,
            rolling_pass_count=7,
            rolling14_pass=True,
            rolling14_pass_count=14,
        ),
    )
    assert out["summary"]["verdict"] == "S8_PASS"
    assert out["summary"]["legacy_verdict"] == "S8_PASS"
    assert out["summary"]["s8_pass_ratio"] == 1.0


def test_evaluate_s_grade_blocks_s8_when_stress_overhead_too_high():
    full_ab = _full_ab_payload(weighted=1.0, hard_delta=1.0, cross_delta=1.0)
    for bucket in full_ab["buckets"]:
        if bucket["name"] == "cross_module_stress":
            bucket["kpi"]["wall_overhead_sec"] = 0.5
    out = evaluate_s_grade(
        full_ab=full_ab,
        ops_rounds=_ops_payload(
            overhead=0.12,
            overhead_p95=0.19,
            overhead_worst_decile=0.24,
            solve_rate=1.0,
            semantic_rate=1.0,
            first_pass=1.0,
            repair_success=1.0,
            learn_attempt=1.0,
            learn_citation=1.0,
            semantic_contract_verified=1.0,
            rolling_pass=True,
            rolling_pass_count=7,
            rolling14_pass=True,
            rolling14_pass_count=14,
        ),
    )
    assert out["summary"]["verdict"] != "S8_PASS"
    assert out["s8_checks"]["stress_wall_overhead"] is False


def test_evaluate_s_grade_uses_service_track_for_stress_overhead_only():
    full_ab = _full_ab_payload(weighted=1.0, hard_delta=1.0, cross_delta=1.0)
    service_full_ab = _full_ab_payload(weighted=0.5, hard_delta=0.0, cross_delta=0.0)
    for bucket in full_ab["buckets"]:
        if bucket["name"] == "cross_module_stress":
            bucket["kpi"]["wall_overhead_sec"] = 0.9
    for bucket in service_full_ab["buckets"]:
        if bucket["name"] == "cross_module_stress":
            bucket["kpi"]["delta_solve_rate"] = 0.0
            bucket["kpi"]["wall_overhead_sec"] = 0.1

    out = evaluate_s_grade(
        full_ab=full_ab,
        service_full_ab=service_full_ab,
        ops_rounds=_ops_payload(
            overhead=0.08,
            overhead_p95=0.11,
            overhead_worst_decile=0.15,
            solve_rate=1.0,
            semantic_rate=1.0,
            first_pass=1.0,
            repair_success=1.0,
            learn_attempt=1.0,
            learn_citation=1.0,
            semantic_contract_verified=1.0,
            rolling_pass=True,
            rolling_pass_count=7,
            rolling14_pass=True,
            rolling14_pass_count=14,
        ),
    )

    assert out["s9_checks"]["stress_delta_solve_rate"] is True
    assert out["s9_checks"]["stress_wall_overhead"] is True


def test_evaluate_s_grade_reaches_s9_when_extreme_overhead_targets_met():
    out = evaluate_s_grade(
        full_ab=_full_ab_payload(weighted=1.0, hard_delta=1.0, cross_delta=1.0),
        ops_rounds=_ops_payload(
            overhead=0.08,
            overhead_p95=0.11,
            overhead_worst_decile=0.15,
            solve_rate=1.0,
            semantic_rate=1.0,
            first_pass=1.0,
            repair_success=1.0,
            learn_attempt=1.0,
            learn_citation=1.0,
            semantic_contract_verified=1.0,
            rolling_pass=True,
            rolling_pass_count=7,
            rolling14_pass=True,
            rolling14_pass_count=14,
        ),
    )
    assert out["summary"]["verdict"] == "S9_PASS"
    assert out["summary"]["legacy_verdict"] == "S9_PASS"
    assert out["summary"]["s9_pass_ratio"] == 1.0


def test_evaluate_s_grade_blocks_s9_when_overhead_exceeds_ceiling():
    out = evaluate_s_grade(
        full_ab=_full_ab_payload(weighted=1.0, hard_delta=1.0, cross_delta=1.0),
        ops_rounds=_ops_payload(
            overhead=0.10,
            overhead_p95=0.13,
            overhead_worst_decile=0.15,
            solve_rate=1.0,
            semantic_rate=1.0,
            first_pass=1.0,
            repair_success=1.0,
            learn_attempt=1.0,
            learn_citation=1.0,
            semantic_contract_verified=1.0,
            rolling_pass=True,
            rolling_pass_count=7,
            rolling14_pass=True,
            rolling14_pass_count=14,
        ),
    )
    assert out["summary"]["verdict"] != "S9_PASS"
    assert out["s9_checks"]["ops_overhead"] is False


def test_evaluate_s_grade_reaches_s10_when_s10_rules_met():
    full_ab = _full_ab_payload(weighted=1.0, hard_delta=0.9, cross_delta=0.9)
    for bucket in full_ab["buckets"]:
        if bucket["name"] == "cross_module_stress":
            bucket["kpi"]["delta_solve_rate"] = 0.9
            bucket["kpi"]["wall_overhead_sec"] = 0.15
    out = evaluate_s_grade(
        full_ab=full_ab,
        ops_rounds=_ops_payload(
            overhead=0.05,
            overhead_p95=0.07,
            overhead_worst_decile=0.09,
            solve_rate=1.0,
            semantic_rate=1.0,
            first_pass=1.0,
            repair_success=1.0,
            learn_attempt=1.0,
            learn_citation=1.0,
            semantic_contract_verified=1.0,
            rolling_pass=True,
            rolling_pass_count=7,
            rolling14_pass=True,
            rolling14_pass_count=14,
        ),
    )
    assert out["summary"]["verdict"] == "S10_PASS"
    assert out["summary"]["legacy_verdict"] == "S10_PASS"
    assert out["summary"]["s10_pass_ratio"] == 1.0


def test_evaluate_s_grade_blocks_s10_when_s10_overhead_not_met():
    full_ab = _full_ab_payload(weighted=1.0, hard_delta=0.9, cross_delta=0.9)
    for bucket in full_ab["buckets"]:
        if bucket["name"] == "cross_module_stress":
            bucket["kpi"]["delta_solve_rate"] = 0.9
            bucket["kpi"]["wall_overhead_sec"] = 0.15
    out = evaluate_s_grade(
        full_ab=full_ab,
        ops_rounds=_ops_payload(
            overhead=0.06,
            overhead_p95=0.11,
            overhead_worst_decile=0.09,
            solve_rate=1.0,
            semantic_rate=1.0,
            first_pass=1.0,
            repair_success=1.0,
            learn_attempt=1.0,
            learn_citation=1.0,
            semantic_contract_verified=1.0,
            rolling_pass=True,
            rolling_pass_count=7,
            rolling14_pass=True,
            rolling14_pass_count=14,
        ),
    )
    assert out["summary"]["verdict"] != "S10_PASS"
    assert out["s10_checks"]["ops_overhead"] is False


def test_evaluate_s_grade_blocks_s10_flash_bucket_without_llm_calls():
    full_ab = _full_ab_payload(
        weighted=1.0,
        hard_delta=0.9,
        cross_delta=0.9,
        flash_file_task=True,
        flash_model_calls=0.0,
    )
    for bucket in full_ab["buckets"]:
        if bucket["name"] == "cross_module_stress":
            bucket["kpi"]["delta_solve_rate"] = 0.9
            bucket["kpi"]["wall_overhead_sec"] = 0.15
    out = evaluate_s_grade(
        full_ab=full_ab,
        ops_rounds=_ops_payload(
            overhead=0.05,
            overhead_p95=0.07,
            overhead_worst_decile=0.09,
            solve_rate=1.0,
            semantic_rate=1.0,
            first_pass=1.0,
            repair_success=1.0,
            learn_attempt=1.0,
            learn_citation=1.0,
            semantic_contract_verified=1.0,
            rolling_pass=True,
            rolling_pass_count=7,
            rolling14_pass=True,
            rolling14_pass_count=14,
        ),
    )
    assert out["summary"]["verdict"] != "S10_PASS"
    assert out["s10_checks"]["flash_file_task_llm_used"] is False


def test_evaluate_s_grade_reads_flash_llm_fields_from_ab_eval_when_kpi_is_legacy():
    full_ab = _full_ab_payload(weighted=1.0, hard_delta=0.9, cross_delta=0.9)
    for bucket in full_ab["buckets"]:
        if bucket["name"] == "cross_module_stress":
            bucket["kpi"]["delta_solve_rate"] = 0.9
            bucket["kpi"]["wall_overhead_sec"] = 0.15
    full_ab["buckets"].append(
        {
            "name": "flash_file_task_cross_module",
            "kpi": {
                "with_solve_rate": 1.0,
                "with_semantic_verified_rate": 1.0,
                "with_trust_mismatch_rate": 0.0,
                "wall_overhead_sec": 45.0,
            },
            "ab_eval": {
                "b": {
                    "summary": {
                        "avg_model_calls": 1.0,
                        "token_measured_rate": 1.0,
                    }
                }
            },
        }
    )
    out = evaluate_s_grade(
        full_ab=full_ab,
        ops_rounds=_ops_payload(
            overhead=0.05,
            overhead_p95=0.07,
            overhead_worst_decile=0.09,
            solve_rate=1.0,
            semantic_rate=1.0,
            first_pass=1.0,
            repair_success=1.0,
            learn_attempt=1.0,
            learn_citation=1.0,
            semantic_contract_verified=1.0,
            rolling_pass=True,
            rolling_pass_count=7,
            rolling14_pass=True,
            rolling14_pass_count=14,
        ),
    )
    assert out["s10_checks"]["flash_file_task_llm_used"] is True
    assert out["s10_checks"]["flash_file_task_tokens_measured"] is True


def test_evaluate_s_grade_reports_realism_s_when_solve_delta_track_is_a_pass():
    out = evaluate_s_grade(
        full_ab=_full_ab_payload(
            weighted=0.6375,
            hard_delta=0.0,
            cross_delta=0.0,
            flash_file_task=True,
            realism_score=0.925,
            flash_wall_overhead=31.0,
        ),
        ops_rounds=_ops_payload(
            overhead=0.05,
            overhead_p95=0.07,
            overhead_worst_decile=0.09,
            solve_rate=1.0,
            semantic_rate=1.0,
            first_pass=1.0,
            repair_success=1.0,
            learn_attempt=1.0,
            learn_citation=1.0,
            semantic_contract_verified=1.0,
            rolling_pass=True,
            rolling_pass_count=7,
            rolling14_pass=True,
            rolling14_pass_count=14,
        ),
    )
    assert out["summary"]["verdict"] == "A_PASS"
    assert out["summary"]["realism_verdict"] == "REALISM_S_PASS"
    assert out["summary"]["realism_s_pass_ratio"] == 1.0
    assert out["summary"]["realism_s_plus_pass_ratio"] < 1.0


def test_evaluate_s_grade_blocks_realism_s10_when_flash_overhead_too_high():
    out = evaluate_s_grade(
        full_ab=_full_ab_payload(
            weighted=1.0,
            hard_delta=1.0,
            cross_delta=1.0,
            flash_file_task=True,
            realism_score=0.99,
            flash_wall_overhead=30.0,
        ),
        ops_rounds=_ops_payload(
            overhead=0.05,
            overhead_p95=0.07,
            overhead_worst_decile=0.09,
            solve_rate=1.0,
            semantic_rate=1.0,
            first_pass=1.0,
            repair_success=1.0,
            learn_attempt=1.0,
            learn_citation=1.0,
            semantic_contract_verified=1.0,
            rolling_pass=True,
            rolling_pass_count=7,
            rolling14_pass=True,
            rolling14_pass_count=14,
        ),
    )
    assert out["summary"]["realism_verdict"] == "REALISM_S_PLUS"
    assert out["realism_s10_checks"]["flash_file_task_wall_overhead"] is False
