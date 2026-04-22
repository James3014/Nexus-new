from pathlib import Path

from scripts.bench.capability_ops_loop import run_ops_loop


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
    assert out["max_tasks"] == 6
    assert out["paths"]["ab_eval_file"]
    assert Path(out["report_file"]).exists()
