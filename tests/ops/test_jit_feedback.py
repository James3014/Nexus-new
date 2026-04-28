import json

from scripts.ops.jit_feedback import build_impact_stats, build_missed_candidates, main


def test_build_missed_candidates_marks_nightly_failure_not_selected():
    rows = [
        {
            "mode": "changed-only",
            "timestamp": "t1",
            "targets": ["tests/a.py"],
            "metadata": {"changed_paths": ["nexus/a.py"]},
        },
        {
            "mode": "nightly-full",
            "timestamp": "t2",
            "success": False,
            "failed_targets": ["tests/b.py"],
        },
    ]

    report = build_missed_candidates(rows)

    assert report["missed_count"] == 1
    assert report["missed_candidates"][0]["target"] == "tests/b.py"
    assert report["missed_candidates"][0]["changed_paths"] == ["nexus/a.py"]


def test_build_impact_stats_combines_observations_and_missed_candidates():
    observations = [
        {
            "changed_paths": ["nexus/a.py"],
            "targets": ["tests/a.py"],
            "success": False,
            "target_durations": {"tests/a.py": 4.0},
        }
    ]
    missed = {
        "missed_candidates": [
            {"target": "tests/b.py", "changed_paths": ["nexus/a.py"]},
        ]
    }

    stats = build_impact_stats(observations, missed)

    assert stats["schema"] == "nexus_test_impact_stats_v1"
    assert stats["mappings"]["nexus/a.py"]["tests/a.py"]["failures"] == 1
    assert stats["mappings"]["nexus/a.py"]["tests/b.py"]["missed_count"] == 1


def test_main_writes_missed_and_stats(tmp_path):
    observations = tmp_path / "jit_observation.jsonl"
    history = tmp_path / "test_history.jsonl"
    observations.write_text(
        json.dumps({"changed_paths": ["nexus/a.py"], "targets": ["tests/a.py"], "success": True}) + "\n",
        encoding="utf-8",
    )
    history.write_text(
        "\n".join(
            [
                json.dumps({"mode": "changed-only", "targets": ["tests/a.py"], "metadata": {"changed_paths": ["nexus/a.py"]}}),
                json.dumps({"mode": "nightly-full", "success": False, "failed_targets": ["tests/b.py"]}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    missed = tmp_path / "missed.json"
    stats = tmp_path / "stats.json"

    assert main(["--observations", str(observations), "--history", str(history), "--missed-output", str(missed), "--stats-output", str(stats)]) == 0

    assert json.loads(missed.read_text(encoding="utf-8"))["missed_count"] == 1
    assert "nexus/a.py" in json.loads(stats.read_text(encoding="utf-8"))["mappings"]
