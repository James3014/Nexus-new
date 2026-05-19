from __future__ import annotations

import json

from scripts.ops.build_evidence_dataset_manifest import (
    build_manifest_from_benchmark_jsonl,
    build_manifest_from_sf_smoke_json,
)


def _write_jsonl(path, rows):
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def test_build_manifest_from_benchmark_jsonl_writes_records(tmp_path):
    source = tmp_path / "benchmark.jsonl"
    output = tmp_path / "evidence_manifest.json"
    _write_jsonl(
        source,
        [
            {
                "task_id": "flash-001",
                "capability": "repair_loop",
                "skill_id": "tdd",
                "status": "SUCCESS",
                "modelcalls": 1,
                "provider_token_measured": True,
                "totaltokens": 1234,
                "evidence_bundle_file": "evidence.json",
            },
            {
                "task_id": "flash-002",
                "capability": "research",
                "status": "FAILED",
                "modelcalls": 1,
            },
        ],
    )

    summary = build_manifest_from_benchmark_jsonl(input_path=source, output_path=output)
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert summary["status"] == "PASS"
    assert summary["record_count"] == 2
    assert summary["public_benchmark_allowed"] is False
    assert payload["rows"][0]["provider_token_cleanliness"] == "measured"
    assert payload["rows"][1]["provider_token_cleanliness"] == "missing"


def test_build_manifest_from_benchmark_jsonl_dry_run_does_not_write(tmp_path):
    source = tmp_path / "benchmark.jsonl"
    output = tmp_path / "evidence_manifest.json"
    _write_jsonl(source, [{"task_id": "flash-001", "capability": "repair_loop", "status": "SUCCESS"}])

    summary = build_manifest_from_benchmark_jsonl(input_path=source, output_path=output, dry_run=True)

    assert summary["status"] == "PASS"
    assert summary["dry_run"] is True
    assert output.exists() is False


def test_build_manifest_from_sf_smoke_json_writes_runtime_apply_review(tmp_path):
    source = tmp_path / "sf_smoke.json"
    output = tmp_path / "evidence_manifest.json"
    source.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "capability": "artifact_gate",
                        "expected_skill": "sf-systematic-artifact_gate-differential-review-461fbd0c",
                        "runtime_final_receipt_chain": {
                            "selected": True,
                            "injected": True,
                            "used": True,
                            "evidence_present": True,
                            "gate_passed": True,
                            "outcome_contributed": True,
                        },
                        "blocking_skill_mount_violations": [],
                        "status": "PASS",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    summary = build_manifest_from_sf_smoke_json(input_path=source, output_path=output)
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert summary["status"] == "PASS"
    assert summary["runtime_update_allowed"] is True
    assert payload["claim_class"] == "RUNTIME_APPLY_REVIEW"
    assert payload["rows"][0]["skill_effect_status"] == "receipt_confirmed"
