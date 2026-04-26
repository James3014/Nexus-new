from scripts.bench.capability_regression_guard import evaluate_regression_guard


def _s_grade_payload(
    *,
    verdict: str = "S6_PASS",
    pass_ratio: float = 1.0,
    weighted: float = 1.0,
    overhead_p95: float = 0.08,
    overhead_worst: float = 0.09,
    trust_mismatch: float = 0.0,
    learn_citation: float = 1.0,
) -> dict:
    return {
        "summary": {"verdict": verdict, "pass_ratio": pass_ratio},
        "inputs": {
            "full_ab_weighted_score": weighted,
            "ops_kpi_median_3round": {
                "wall_overhead_p95_sec": overhead_p95,
                "wall_overhead_worst_decile_mean_sec": overhead_worst,
            },
            "anti_hallucination": {"report_trust_mismatch_rate": trust_mismatch},
            "capability_paths": {"learn_mode_citation_usage_rate": learn_citation},
        },
    }


def test_regression_guard_passes_when_current_meets_or_exceeds_baseline():
    baseline = _s_grade_payload()
    current = _s_grade_payload(overhead_p95=0.06, overhead_worst=0.07)
    out = evaluate_regression_guard(
        current_s_grade=current,
        baseline_s_grade=baseline,
        service_full_ab=None,
        min_grade="S6_PASS",
        max_weighted_drop=0.01,
        max_pass_ratio_drop=0.03,
        max_overhead_p95_increase=0.1,
        max_overhead_worst_decile_increase=0.1,
        max_trust_mismatch_increase=0.0,
        max_learn_citation_drop=0.1,
        service_weighted_score_min=0.55,
        service_daily_delta_solve_rate_min=-0.02,
        service_hard_delta_solve_rate_min=-0.02,
        service_cross_delta_solve_rate_min=-0.02,
        service_stress_delta_solve_rate_min=-0.02,
        service_trust_mismatch_max=0.0,
        service_daily_wall_overhead_sec_max=0.2,
        service_hard_wall_overhead_sec_max=0.2,
        service_cross_wall_overhead_sec_max=0.8,
        service_stress_wall_overhead_sec_max=0.3,
    )
    assert out["status"] == "PASS"
    assert out["failures"] == []


def test_regression_guard_fails_on_grade_drop_and_overhead_regression():
    baseline = _s_grade_payload(verdict="S6_PASS", overhead_p95=0.05, overhead_worst=0.06)
    current = _s_grade_payload(verdict="S4_PASS", overhead_p95=0.3, overhead_worst=0.25)
    out = evaluate_regression_guard(
        current_s_grade=current,
        baseline_s_grade=baseline,
        service_full_ab=None,
        min_grade="S6_PASS",
        max_weighted_drop=0.01,
        max_pass_ratio_drop=0.03,
        max_overhead_p95_increase=0.1,
        max_overhead_worst_decile_increase=0.1,
        max_trust_mismatch_increase=0.0,
        max_learn_citation_drop=0.1,
        service_weighted_score_min=0.55,
        service_daily_delta_solve_rate_min=-0.02,
        service_hard_delta_solve_rate_min=-0.02,
        service_cross_delta_solve_rate_min=-0.02,
        service_stress_delta_solve_rate_min=-0.02,
        service_trust_mismatch_max=0.0,
        service_daily_wall_overhead_sec_max=0.2,
        service_hard_wall_overhead_sec_max=0.2,
        service_cross_wall_overhead_sec_max=0.8,
        service_stress_wall_overhead_sec_max=0.3,
    )
    assert out["status"] == "FAIL"
    assert any("grade_below_min" in item for item in out["failures"])
    assert any("ops_overhead_p95_regression" in item for item in out["failures"])


def test_regression_guard_fails_when_service_track_regresses():
    baseline = _s_grade_payload()
    current = _s_grade_payload(overhead_p95=0.06, overhead_worst=0.07)
    service_full_ab = {
        "weighted_score": 0.7,
        "buckets": [
            {"name": "daily", "kpi": {"delta_solve_rate": 0.0, "with_trust_mismatch_rate": 0.0, "wall_overhead_sec": 0.05}},
            {"name": "hard", "kpi": {"delta_solve_rate": 0.0, "with_trust_mismatch_rate": 0.0, "wall_overhead_sec": 0.05}},
            {
                "name": "cross_module",
                "kpi": {"delta_solve_rate": -0.2, "with_trust_mismatch_rate": 0.0, "wall_overhead_sec": 0.2},
            },
            {
                "name": "cross_module_stress",
                "kpi": {"delta_solve_rate": 0.0, "with_trust_mismatch_rate": 0.0, "wall_overhead_sec": 0.1},
            },
        ],
    }
    out = evaluate_regression_guard(
        current_s_grade=current,
        baseline_s_grade=baseline,
        service_full_ab=service_full_ab,
        min_grade="S6_PASS",
        max_weighted_drop=0.01,
        max_pass_ratio_drop=0.03,
        max_overhead_p95_increase=0.1,
        max_overhead_worst_decile_increase=0.1,
        max_trust_mismatch_increase=0.0,
        max_learn_citation_drop=0.1,
        service_weighted_score_min=0.55,
        service_daily_delta_solve_rate_min=-0.02,
        service_hard_delta_solve_rate_min=-0.02,
        service_cross_delta_solve_rate_min=-0.02,
        service_stress_delta_solve_rate_min=-0.02,
        service_trust_mismatch_max=0.0,
        service_daily_wall_overhead_sec_max=0.2,
        service_hard_wall_overhead_sec_max=0.2,
        service_cross_wall_overhead_sec_max=0.8,
        service_stress_wall_overhead_sec_max=0.3,
    )
    assert out["status"] == "FAIL"
    assert any("service_cross_delta_solve_rate_below_min" in item for item in out["failures"])


def test_regression_guard_respects_grade_order_for_s2_vs_s9():
    baseline = _s_grade_payload(verdict="S9_PASS")
    current = _s_grade_payload(verdict="S2_PASS")
    out = evaluate_regression_guard(
        current_s_grade=current,
        baseline_s_grade=baseline,
        service_full_ab=None,
        min_grade="S9_PASS",
        max_weighted_drop=0.01,
        max_pass_ratio_drop=0.03,
        max_overhead_p95_increase=0.1,
        max_overhead_worst_decile_increase=0.1,
        max_trust_mismatch_increase=0.0,
        max_learn_citation_drop=0.1,
        service_weighted_score_min=0.55,
        service_daily_delta_solve_rate_min=-0.02,
        service_hard_delta_solve_rate_min=-0.02,
        service_cross_delta_solve_rate_min=-0.02,
        service_stress_delta_solve_rate_min=-0.02,
        service_trust_mismatch_max=0.0,
        service_daily_wall_overhead_sec_max=0.2,
        service_hard_wall_overhead_sec_max=0.2,
        service_cross_wall_overhead_sec_max=0.8,
        service_stress_wall_overhead_sec_max=0.3,
    )
    assert out["status"] == "FAIL"
    assert any("grade_below_min" in item for item in out["failures"])


def test_regression_guard_prefers_duration_ratio_when_service_metric_is_duration():
    baseline = _s_grade_payload()
    current = _s_grade_payload()
    service_full_ab = {
        "weighted_score": 0.7,
        "buckets": [
            {
                "name": "daily",
                "kpi": {
                    "delta_solve_rate": 0.0,
                    "with_trust_mismatch_rate": 0.0,
                    "wall_overhead_sec": 0.6,
                    "overhead_metric": "avg_duration_sec",
                    "with_avg_duration_sec": 1.2,
                    "without_avg_duration_sec": 2.0,
                    "with_avg_wall_duration_sec": 2.5,
                    "without_avg_wall_duration_sec": 0.8,
                },
            }
        ],
    }
    out = evaluate_regression_guard(
        current_s_grade=current,
        baseline_s_grade=baseline,
        service_full_ab=service_full_ab,
        min_grade="S6_PASS",
        max_weighted_drop=0.01,
        max_pass_ratio_drop=0.03,
        max_overhead_p95_increase=0.1,
        max_overhead_worst_decile_increase=0.1,
        max_trust_mismatch_increase=0.0,
        max_learn_citation_drop=0.1,
        service_weighted_score_min=0.55,
        service_daily_delta_solve_rate_min=-0.02,
        service_hard_delta_solve_rate_min=-0.02,
        service_cross_delta_solve_rate_min=-0.02,
        service_stress_delta_solve_rate_min=-0.02,
        service_trust_mismatch_max=0.0,
        service_daily_wall_overhead_sec_max=1.0,
        service_hard_wall_overhead_sec_max=1.0,
        service_cross_wall_overhead_sec_max=1.0,
        service_stress_wall_overhead_sec_max=1.0,
        service_daily_wall_overhead_ratio_max=0.5,
        service_hard_wall_overhead_ratio_max=0.5,
        service_cross_wall_overhead_ratio_max=0.6,
        service_stress_wall_overhead_ratio_max=0.6,
    )
    assert out["status"] == "PASS"
