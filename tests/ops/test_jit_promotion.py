from __future__ import annotations

import json

from scripts.ops.jit_promotion import build_promotion_report, main


def _observation(index: int, **overrides):
    row = {
        "event": "changed_only",
        "changed_paths": [f"nexus/core/file_{index}.py"],
        "targets": ["tests/core"],
        "fallback_used": False,
        "unmatched_paths": [],
        "predictive_saved_runtime_sec": 1.5,
    }
    row.update(overrides)
    return row


def test_build_promotion_report_promotes_when_evidence_is_clean():
    report = build_promotion_report(
        [_observation(i) for i in range(3)],
        [{"mode": "nightly-full", "success": True}],
        {"missed_count": 0, "missed_candidates": []},
        {"mappings": {"nexus/core/file_1.py": {"tests/core": {"score": 3.0}}}},
        min_observations=3,
        min_nightly_full=1,
    )

    assert report["schema"] == "nexus_jit_predictive_promotion_v1"
    assert report["verdict"] == "PROMOTE_CANDIDATE"
    assert report["eligible_observation_count"] == 3
    assert report["miss_rate"] == 0.0
    assert report["predictive_saved_runtime_sec"] == 4.5
    assert report["stats_target_count"] == 1


def test_build_promotion_report_holds_on_missed_candidate():
    report = build_promotion_report(
        [_observation(1)],
        [{"mode": "nightly-full", "success": False}],
        {"missed_count": 1, "missed_candidates": [{"target": "tests/services"}]},
        {"mappings": {}},
        min_observations=1,
        min_nightly_full=1,
    )

    assert report["verdict"] == "HOLD"
    assert report["criteria"]["miss_rate"] is False
    assert report["miss_rate"] == 1.0


def test_jit_promotion_cli_writes_report(tmp_path):
    observations = tmp_path / "jit_observation.jsonl"
    history = tmp_path / "test_history.jsonl"
    missed = tmp_path / "missed.json"
    stats = tmp_path / "stats.json"
    output = tmp_path / "promotion.json"
    observations.write_text(json.dumps(_observation(1)) + "\n", encoding="utf-8")
    history.write_text(json.dumps({"mode": "nightly-full", "success": True}) + "\n", encoding="utf-8")
    missed.write_text(json.dumps({"missed_count": 0, "missed_candidates": []}), encoding="utf-8")
    stats.write_text(json.dumps({"mappings": {}}), encoding="utf-8")

    exit_code = main(
        [
            "--observations",
            str(observations),
            "--history",
            str(history),
            "--missed-report",
            str(missed),
            "--stats",
            str(stats),
            "--output",
            str(output),
            "--min-observations",
            "1",
            "--min-nightly-full",
            "1",
        ]
    )

    assert exit_code == 0
    assert json.loads(output.read_text(encoding="utf-8"))["verdict"] == "PROMOTE_CANDIDATE"
