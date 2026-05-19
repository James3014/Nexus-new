from __future__ import annotations

import json

from scripts.ops.check_optimization_artifact_hygiene import check_optimization_artifact_hygiene


def _read_model(**overrides):
    payload = {
        "claim_class": "RUNTIME_APPLY_REVIEW",
        "provider_token_cleanliness": "not_applicable",
        "evidence_bundle_refs": ["docs/reports/evidence.json"],
        "receipt_refs": ["docs/reports/receipt.json"],
        "runtime_update_allowed": False,
        "public_benchmark_allowed": False,
        "gates": [
            {"name": "delivery", "status": "PASS"},
            {"name": "trust", "status": "PASS"},
            {"name": "artifact", "status": "PASS"},
            {"name": "receipt", "status": "PASS"},
            {"name": "claim", "status": "PASS"},
        ],
    }
    payload.update(overrides)
    return payload


def test_hygiene_hook_passes_clean_read_model_and_retention_manifest(tmp_path):
    read_model = tmp_path / "read_model.json"
    retention = tmp_path / "retention.json"
    output = tmp_path / "hygiene.json"
    read_model.write_text(json.dumps(_read_model()), encoding="utf-8")
    retention.write_text(json.dumps({"status": "PASS", "summary": {"blocker_count": 0}}), encoding="utf-8")

    payload = check_optimization_artifact_hygiene(
        read_model_path=read_model,
        retention_manifest_path=retention,
        output_path=output,
    )

    assert payload["status"] == "PASS"
    assert payload["blockers"] == []
    assert output.exists() is True


def test_hygiene_hook_blocks_read_model_unlock_attempt(tmp_path):
    read_model = tmp_path / "read_model.json"
    read_model.write_text(json.dumps(_read_model(runtime_update_allowed=True)), encoding="utf-8")

    payload = check_optimization_artifact_hygiene(read_model_path=read_model)

    assert payload["status"] == "RETURN"
    assert "read_model:read_model_must_not_update_runtime" in payload["blockers"]
    assert "read_model:runtime_update_allowed" in payload["blockers"]


def test_hygiene_hook_blocks_retention_manifest_with_blockers(tmp_path):
    read_model = tmp_path / "read_model.json"
    retention = tmp_path / "retention.json"
    read_model.write_text(json.dumps(_read_model()), encoding="utf-8")
    retention.write_text(json.dumps({"status": "RETURN", "summary": {"blocker_count": 1}}), encoding="utf-8")

    payload = check_optimization_artifact_hygiene(
        read_model_path=read_model,
        retention_manifest_path=retention,
        dry_run=True,
    )

    assert payload["status"] == "RETURN"
    assert payload["dry_run"] is True
    assert payload["blockers"] == [
        "retention_manifest:blockers_present",
        "retention_manifest:not_pass",
    ]
