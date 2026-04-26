from pathlib import Path

from scripts.bench.capability_ops_loop import (
    _compute_health_score,
    _compute_overhead_breakdown,
    _compute_pillar_scores,
    _compute_route_consensus_metrics,
    _extract_first_pass_blockers,
    run_ops_loop,
    run_ops_loop_rounds,
)


def test_run_ops_loop_smoke_without_autotune(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[2]
    output_dir = tmp_path / "ops"
    out = run_ops_loop(
        repo_root=repo_root,
        profile="daily",
        output_dir=output_dir,
        apply_autotune=False,
    )
    assert out["status"] == "SUCCESS"
    assert out["profile"] == "daily"
    assert out["with_llm_mode"] == "off"
    assert out["max_tasks"] == 6
    assert out["paths"]["ab_eval_file"]
    assert "kpi" in out
    assert out["health"]["verdict"] in {"PASS", "WARN"}
    assert "pillars" in out
    assert "self_heal" in out
    assert "first_pass_blockers" in out
    assert "overhead_breakdown" in out
    assert "route_consensus" in out
    assert 0.0 <= out["pillars"]["overall"] <= 1.0
    assert Path(out["report_file"]).exists()


def test_run_ops_loop_rounds_outputs_median_kpi(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[2]
    output_dir = tmp_path / "ops_rounds"
    out = run_ops_loop_rounds(
        repo_root=repo_root,
        profile="daily",
        output_dir=output_dir,
        apply_autotune=False,
        rounds=2,
    )
    assert out["rounds"] == 2
    assert "kpi_median_3round" in out
    assert out["trend_gate"]["verdict"] in {"PASS", "WARN"}
    assert "median_consensus" in out["trend_gate"]
    assert Path(out["report_file"]).exists()


def test_compute_health_score_warns_on_low_quality():
    payload = {
        "a": {"summary": {"solve_rate": 0.8, "semantic_verified_rate": 0.7, "trust_mismatch_rate": 0.1, "avg_wall_duration_sec": 1.5}},
        "b": {"summary": {"avg_wall_duration_sec": 0.5}},
    }
    out = _compute_health_score(payload)
    assert out["verdict"] == "WARN"
    assert 0.0 <= out["score"] <= 1.0


def test_memory_pillar_uses_route_memory_hits_only():
    out = _compute_pillar_scores(
        [
            {"route_findings_hits": 2, "prior_fix_hits": 2, "route_memory_hits": 0},
            {"route_findings_hits": 0, "prior_fix_hits": 1, "route_memory_hits": 1},
        ]
    )
    assert out["scores"]["LanceDB"] == 0.5
    assert out["scores"]["Memory"] == 0.5


def test_route_consensus_treats_hyper_fastpath_baseline_as_aligned():
    out = _compute_route_consensus_metrics(
        [
            {
                "route_consensus_winner": "hyper_sprint",
                "route_recommended_flow": "hyper_sprint",
                "chosen_flow": "baseline",
                "strategy_path": "probe_success_fastpath_baseline",
                "capability_self_heal_used": True,
                "route_consensus_hyper_votes": 1,
                "route_consensus_baseline_votes": 0,
            },
            {
                "route_consensus_winner": "baseline",
                "route_recommended_flow": "baseline",
                "chosen_flow": "baseline",
                "route_consensus_hyper_votes": 0,
                "route_consensus_baseline_votes": 1,
            },
        ]
    )
    assert out["winner_match_recommended_rate"] == 1.0
    assert out["winner_match_chosen_flow_rate"] == 1.0


def test_overhead_breakdown_identifies_top_phase():
    out = _compute_overhead_breakdown(
        [
            {"wall_duration_sec": 1.0, "subprocess_wall_sec": 1.0, "cli_elapsed_sec": 0.9, "phase_wall_p_sec": 0.1, "phase_wall_r_sec": 0.7},
            {"wall_duration_sec": 1.2, "subprocess_wall_sec": 1.2, "cli_elapsed_sec": 1.1, "phase_wall_p_sec": 0.2, "phase_wall_r_sec": 0.8},
        ],
        [{"wall_duration_sec": 0.4}, {"wall_duration_sec": 0.5}],
    )
    assert out["wall_overhead_sec"] == 0.65
    assert out["top_phase"] == "R"
    assert out["phase_avg_sec"]["R"] == 0.75


def test_extract_first_pass_blockers_reports_attempt_rows():
    out = _extract_first_pass_blockers(
        [
            {"task_id": "a", "attempt_count": 1},
            {
                "task_id": "b",
                "attempt_count": 2,
                "status": "SUCCESS",
                "strategy_path": "probe_then_hyper",
                "chosen_flow": "hyper_sprint",
                "route_recommended_flow": "hyper_sprint",
                "phase_wall_r_sec": 2.0,
                "wall_duration_sec": 2.2,
            },
        ]
    )
    assert out == [
        {
            "task_id": "b",
            "attempt_count": 2,
            "status": "SUCCESS",
            "strategy_path": "probe_then_hyper",
            "chosen_flow": "hyper_sprint",
            "route_recommended_flow": "hyper_sprint",
            "phase_wall_r_sec": 2.0,
            "wall_duration_sec": 2.2,
        }
    ]
