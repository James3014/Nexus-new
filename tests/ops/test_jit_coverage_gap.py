import json

from scripts.ops.jit_coverage_gap import build_coverage_gap_report, main


def test_build_coverage_gap_report_counts_fallback_and_unmatched_paths():
    rows = [
        {
            "changed_paths": ["docs/a.md", "nexus/core/state.py"],
            "fallback_used": True,
            "high_risk_escalated": True,
            "unmatched_paths": ["docs/a.md"],
            "target_durations": {"tests/core": 1.5, "tests/ops/test_select_tests.py": 0.1},
        },
        {
            "changed_paths": ["docs/a.md"],
            "fallback_used": True,
            "high_risk_escalated": False,
            "unmatched_paths": ["docs/a.md"],
            "target_durations": {"tests/core": 1.2},
        },
    ]

    report = build_coverage_gap_report(rows, limit=5)

    assert report["schema"] == "nexus_jit_coverage_gap_v1"
    assert report["observation_count"] == 2
    assert report["fallback_run_count"] == 2
    assert report["fallback_heavy_paths"][0] == {"value": "docs/a.md", "count": 2}
    assert report["unmatched_paths"][0] == {"value": "docs/a.md", "count": 2}
    assert report["high_risk_paths"][0] == {"value": "docs/a.md", "count": 1}
    assert report["slow_generic_targets"][0] == {"value": "tests/core", "count": 2}


def test_main_writes_coverage_gap_report(tmp_path, capsys):
    src = tmp_path / "jit_observation.jsonl"
    out = tmp_path / "jit_coverage_gap.json"
    src.write_text(
        json.dumps({"changed_paths": ["docs/a.md"], "fallback_used": True, "unmatched_paths": ["docs/a.md"]}) + "\n",
        encoding="utf-8",
    )

    assert main(["--input", str(src), "--output", str(out)]) == 0

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["fallback_heavy_paths"] == [{"value": "docs/a.md", "count": 1}]
    assert json.loads(capsys.readouterr().out)["status"] == "SUCCESS"
