import json
import subprocess
from pathlib import Path

from scripts.bench.capability_autotune import compute_tuning


def test_compute_tuning_expands_budget_when_solve_rate_low():
    payload = {
        "a": {"summary": {"solve_rate": 0.7, "trust_mismatch_rate": 0.0, "avg_wall_duration_sec": 1.3}},
        "b": {"summary": {"avg_wall_duration_sec": 0.4}},
    }
    out = compute_tuning(payload)
    assert out["knobs"]["candidate_boost"] == 1
    assert out["knobs"]["max_rounds_boost"] == 1
    assert out["knobs"]["skip_baseline_probe_for_hard"] is False
    assert "protect_solve_rate_keep_hard_probe" in out["reasons"]


def test_compute_tuning_keeps_conservative_when_trust_mismatch_detected():
    payload = {
        "a": {"summary": {"solve_rate": 1.0, "trust_mismatch_rate": 0.3, "avg_wall_duration_sec": 1.0}},
        "b": {"summary": {"avg_wall_duration_sec": 0.7}},
    }
    out = compute_tuning(payload)
    assert "trust_mismatch_detected_keep_conservative" in out["reasons"]
    assert out["knobs"]["baseline_fast_sec"] == 0.0
    assert out["knobs"]["skip_baseline_probe_for_hard"] is False


def test_compute_tuning_enables_hard_probe_skip_only_with_strong_quality():
    payload = {
        "a": {"summary": {"solve_rate": 0.98, "trust_mismatch_rate": 0.0, "avg_wall_duration_sec": 1.4}},
        "b": {"summary": {"avg_wall_duration_sec": 0.4}},
    }
    out = compute_tuning(payload)
    assert out["knobs"]["skip_baseline_probe_for_hard"] is True
    assert "strong_quality_enable_hard_probe_skip" in out["reasons"]


def test_compute_tuning_holds_previous_knobs_in_hysteresis_band():
    payload = {
        "a": {"summary": {"solve_rate": 0.95, "trust_mismatch_rate": 0.0, "avg_wall_duration_sec": 1.0}},
        "b": {"summary": {"avg_wall_duration_sec": 0.4}},
    }
    out = compute_tuning(
        payload,
        previous_tuning={
            "knobs": {
                "candidate_boost": 1,
                "max_rounds_boost": 1,
                "stage1_parallel_boost": -1,
                "skip_baseline_probe_for_hard": False,
            }
        },
    )
    assert out["knobs"]["candidate_boost"] == 1
    assert out["knobs"]["max_rounds_boost"] == 1
    assert out["knobs"]["stage1_parallel_boost"] == -1
    assert "solve_rate_hysteresis_hold_previous" in out["reasons"]
    assert "wall_overhead_hysteresis_hold_previous" in out["reasons"]


def test_compute_tuning_uses_median_over_history_payloads():
    current = {
        "a": {"summary": {"solve_rate": 1.0, "trust_mismatch_rate": 0.0, "avg_wall_duration_sec": 1.6}},
        "b": {"summary": {"avg_wall_duration_sec": 0.4}},
    }
    history = [
        {"a": {"summary": {"solve_rate": 0.7, "trust_mismatch_rate": 0.0, "avg_wall_duration_sec": 1.6}}, "b": {"summary": {"avg_wall_duration_sec": 0.4}}},
        {"a": {"summary": {"solve_rate": 1.0, "trust_mismatch_rate": 0.0, "avg_wall_duration_sec": 1.6}}, "b": {"summary": {"avg_wall_duration_sec": 0.4}}},
    ]
    out = compute_tuning(current, history_payloads=history)
    # median solve_rate = 1.0, so expansion should not be enabled.
    assert out["knobs"]["candidate_boost"] == 0
    assert out["aggregation_mode"] == "median"
    assert out["aggregation_window"] == 3


def test_cli_apply_writes_tuning_and_backup(tmp_path: Path):
    eval_file = tmp_path / "ab_eval.json"
    eval_file.write_text(
        json.dumps(
            {
                "a": {"summary": {"solve_rate": 1.0, "trust_mismatch_rate": 0.0, "avg_wall_duration_sec": 1.1}},
                "b": {"summary": {"avg_wall_duration_sec": 0.5}},
            }
        ),
        encoding="utf-8",
    )
    tuning_file = tmp_path / "capability_tuning.json"
    tuning_file.write_text(json.dumps({"old": True}), encoding="utf-8")

    cmd = [
        "uv",
        "run",
        "python",
        "scripts/bench/capability_autotune.py",
        "--eval-file",
        str(eval_file),
        "--tuning-file",
        str(tuning_file),
        "--apply",
        "--output-json",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, cwd=Path(__file__).resolve().parents[2])
    assert res.returncode == 0
    written = json.loads(tuning_file.read_text(encoding="utf-8"))
    assert written["status"] == "SUCCESS"
    assert written["aggregation_mode"] == "median"
    backup = json.loads((tmp_path / "capability_tuning.prev.json").read_text(encoding="utf-8"))
    assert backup["old"] is True
