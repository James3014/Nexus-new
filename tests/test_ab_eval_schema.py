from __future__ import annotations

import json

from scripts.bench.ab_eval import compare_datasets, load_runs


def test_ab_eval_loads_jsonl_and_compares_semantic_solve_rate(tmp_path):
    dataset_a = tmp_path / "a.jsonl"
    dataset_b = tmp_path / "b.jsonl"

    dataset_a.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "task_id": "t1",
                        "semantic_status": "UNVERIFIED",
                        "task_duration_sec": 10.0,
                        "wall_duration_sec": 12.0,
                        "total_tokens": 200,
                        "attempt_count": 1,
                    }
                ),
                json.dumps(
                    {
                        "task_id": "t2",
                        "semantic_status": "VERIFIED",
                        "task_duration_sec": 20.0,
                        "wall_duration_sec": 22.0,
                        "total_tokens": 400,
                        "attempt_count": 2,
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    dataset_b.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "task_id": "t1",
                        "semantic_status": "VERIFIED",
                        "task_duration_sec": 12.0,
                        "wall_duration_sec": 14.0,
                        "total_tokens": 300,
                        "attempt_count": 2,
                    }
                ),
                json.dumps(
                    {
                        "task_id": "t2",
                        "semantic_status": "VERIFIED",
                        "task_duration_sec": 22.0,
                        "wall_duration_sec": 24.0,
                        "total_tokens": 500,
                        "attempt_count": 3,
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    report = compare_datasets("without", load_runs(dataset_a), "with", load_runs(dataset_b))
    assert report["a"]["summary"]["solve_rate"] == 0.5
    assert report["a"]["summary"]["semantic_verified_rate"] == 0.5
    assert report["a"]["summary"]["avg_wall_duration_sec"] == 17.0
    assert report["b"]["summary"]["solve_rate"] == 1.0
    assert report["b"]["summary"]["semantic_verified_rate"] == 1.0
    assert report["b"]["summary"]["avg_wall_duration_sec"] == 19.0
    assert report["delta"]["solve_rate_delta"] == 0.5
    assert report["delta"]["semantic_verified_rate_delta"] == 0.5
    assert report["delta"]["avg_wall_duration_sec_delta"] == 2.0


def test_ab_eval_counts_trust_mismatch_rate(tmp_path):
    dataset_a = tmp_path / "trust_a.json"
    dataset_b = tmp_path / "trust_b.json"
    dataset_a.write_text(
        json.dumps(
            [
                {"semantic_status": "VERIFIED", "report_trust_mismatch": False},
                {"semantic_status": "VERIFIED", "report_trust_mismatch": True},
            ]
        ),
        encoding="utf-8",
    )
    dataset_b.write_text(
        json.dumps(
            [
                {"semantic_status": "VERIFIED", "report_trust_mismatch": False},
                {"semantic_status": "VERIFIED", "report_trust_mismatch": False},
            ]
        ),
        encoding="utf-8",
    )
    report = compare_datasets("a", load_runs(dataset_a), "b", load_runs(dataset_b))
    assert report["a"]["summary"]["trust_mismatch_rate"] == 0.5
    assert report["b"]["summary"]["trust_mismatch_rate"] == 0.0
    assert report["delta"]["trust_mismatch_rate_delta"] == -0.5


def test_ab_eval_treats_null_semantic_status_as_missing_and_falls_back_to_status(tmp_path):
    dataset = tmp_path / "rows.json"
    dataset.write_text(
        json.dumps(
            [
                {"semantic_status": None, "status": "SUCCESS"},
                {"semantic_status": "VERIFIED", "status": "FAILED"},
            ]
        ),
        encoding="utf-8",
    )
    report = compare_datasets("x", load_runs(dataset), "y", load_runs(dataset))
    assert report["a"]["summary"]["solve_rate"] == 1.0
    assert report["a"]["summary"]["semantic_verified_rate"] == 0.5
