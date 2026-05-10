from __future__ import annotations

import json

from scripts.ops.build_autodata_manifest_from_benchmark import build_autodata_manifest_from_benchmark


def _write_jsonl(path, rows):
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def test_build_autodata_manifest_from_benchmark_writes_quality_rows(tmp_path):
    with_nexus = tmp_path / "with.jsonl"
    without_nexus = tmp_path / "without.jsonl"
    output = tmp_path / "autodata.json"
    _write_jsonl(
        with_nexus,
        [
            {
                "task_id": "hard-001",
                "status": "SUCCESS",
                "semantic_status": "VERIFIED",
                "trajectory_step_count": 12,
                "evidence_record_file": "with-hard.row.json",
            }
        ],
    )
    _write_jsonl(
        without_nexus,
        [
            {
                "task_id": "hard-001",
                "status": "FAILED",
                "semantic_status": "UNVERIFIED",
                "trajectory_step_count": 0,
                "evidence_record_file": "without-hard.row.json",
            }
        ],
    )

    summary = build_autodata_manifest_from_benchmark(
        with_nexus=with_nexus,
        without_nexus=without_nexus,
        output=output,
    )
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert summary["passed"] is True
    assert summary["row_count"] == 2
    assert summary["training_eligible_count"] == 1
    assert summary["hard_negative_count"] == 1
    assert payload["rows"][0]["eligible_for_training"] is True
    assert payload["rows"][1]["hard_negative"] is True


def test_build_autodata_manifest_from_benchmark_dry_run_does_not_write(tmp_path):
    with_nexus = tmp_path / "with.jsonl"
    without_nexus = tmp_path / "without.jsonl"
    output = tmp_path / "autodata.json"
    _write_jsonl(with_nexus, [{"task_id": "x", "status": "SUCCESS", "semantic_status": "VERIFIED", "trajectory_step_count": 12}])
    _write_jsonl(without_nexus, [{"task_id": "x", "status": "FAILED", "semantic_status": "UNVERIFIED"}])

    summary = build_autodata_manifest_from_benchmark(
        with_nexus=with_nexus,
        without_nexus=without_nexus,
        output=output,
        dry_run=True,
    )

    assert summary["passed"] is True
    assert summary["dry_run"] is True
    assert output.exists() is False
