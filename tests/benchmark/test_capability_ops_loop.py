from pathlib import Path

from scripts.bench.capability_ops_loop import _compute_health_score, run_ops_loop, run_ops_loop_rounds


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
    assert Path(out["report_file"]).exists()


def test_compute_health_score_warns_on_low_quality():
    payload = {
        "a": {"summary": {"solve_rate": 0.8, "semantic_verified_rate": 0.7, "trust_mismatch_rate": 0.1, "avg_wall_duration_sec": 1.5}},
        "b": {"summary": {"avg_wall_duration_sec": 0.5}},
    }
    out = _compute_health_score(payload)
    assert out["verdict"] == "WARN"
    assert 0.0 <= out["score"] <= 1.0
