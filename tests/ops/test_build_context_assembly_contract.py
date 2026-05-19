from __future__ import annotations

import json

from scripts.ops.build_context_assembly_contract import build_context_assembly_contract_from_source_manifest


def _source_manifest():
    return {
        "sources": [
            {"source_id": "L0:rules", "kind": "L0", "estimated_tokens": 100},
            {"source_id": "L1:index", "kind": "L1", "estimated_tokens": 100},
            {"source_id": "retrieval", "kind": "retrieval", "estimated_tokens": 250, "priority": 10},
            {"source_id": "history", "kind": "history", "estimated_tokens": 300, "priority": 20},
        ]
    }


def test_build_context_assembly_contract_from_source_manifest_writes_artifact(tmp_path):
    source = tmp_path / "context_sources.json"
    output = tmp_path / "context_contract.json"
    source.write_text(json.dumps(_source_manifest()), encoding="utf-8")

    summary = build_context_assembly_contract_from_source_manifest(
        input_path=source,
        output_path=output,
        token_budget=500,
        task_id="ctx-001",
    )
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert summary["status"] == "PASS"
    assert summary["kept_source_count"] == 3
    assert summary["dropped_source_count"] == 1
    assert payload["task_id"] == "ctx-001"
    assert payload["source_manifest_path"] == str(source)


def test_build_context_assembly_contract_from_source_manifest_dry_run(tmp_path):
    source = tmp_path / "context_sources.json"
    output = tmp_path / "context_contract.json"
    source.write_text(json.dumps(_source_manifest()), encoding="utf-8")

    summary = build_context_assembly_contract_from_source_manifest(
        input_path=source,
        output_path=output,
        token_budget=500,
        task_id="ctx-001",
        dry_run=True,
    )

    assert summary["status"] == "PASS"
    assert summary["dry_run"] is True
    assert output.exists() is False


def test_build_context_assembly_contract_returns_for_over_budget_required_sources(tmp_path):
    source = tmp_path / "context_sources.json"
    output = tmp_path / "context_contract.json"
    source.write_text(json.dumps(_source_manifest()), encoding="utf-8")

    summary = build_context_assembly_contract_from_source_manifest(
        input_path=source,
        output_path=output,
        token_budget=150,
        task_id="ctx-001",
    )
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert summary["status"] == "RETURN"
    assert "receipt_not_pass" in payload["blockers"]
