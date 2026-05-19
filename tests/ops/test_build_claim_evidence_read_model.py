from __future__ import annotations

import json

from scripts.ops.build_claim_evidence_read_model import build_read_model_from_evidence_manifest


def _manifest(**overrides):
    payload = {
        "claim_class": "RUNTIME_APPLY_REVIEW",
        "rows": [
            {
                "delivery_status": "PASS",
                "trust_status": "PASS",
                "provider_token_cleanliness": "not_applicable",
                "evidence_refs": ["docs/reports/evidence.json"],
                "receipt_refs": ["docs/reports/receipt.json"],
                "blockers": [],
            }
        ],
    }
    payload.update(overrides)
    return payload


def test_build_read_model_from_evidence_manifest_writes_artifact(tmp_path):
    source = tmp_path / "evidence_manifest.json"
    output = tmp_path / "read_model.json"
    source.write_text(json.dumps(_manifest()), encoding="utf-8")

    summary = build_read_model_from_evidence_manifest(input_path=source, output_path=output)
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert summary["status"] == "PASS"
    assert summary["gate_count"] == 5
    assert summary["runtime_update_allowed"] is False
    assert summary["public_benchmark_allowed"] is False
    assert payload["claim_class"] == "RUNTIME_APPLY_REVIEW"
    assert {gate["name"]: gate["status"] for gate in payload["gates"]}["claim"] == "PASS"


def test_build_read_model_from_evidence_manifest_dry_run_does_not_write(tmp_path):
    source = tmp_path / "evidence_manifest.json"
    output = tmp_path / "read_model.json"
    source.write_text(json.dumps(_manifest()), encoding="utf-8")

    summary = build_read_model_from_evidence_manifest(input_path=source, output_path=output, dry_run=True)

    assert summary["status"] == "PASS"
    assert summary["dry_run"] is True
    assert output.exists() is False


def test_build_read_model_returns_when_manifest_has_no_receipts(tmp_path):
    source = tmp_path / "evidence_manifest.json"
    output = tmp_path / "read_model.json"
    source.write_text(json.dumps(_manifest(rows=[{"delivery_status": "PASS", "trust_status": "PASS"}])), encoding="utf-8")

    summary = build_read_model_from_evidence_manifest(input_path=source, output_path=output)
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert summary["status"] == "RETURN"
    assert "missing_receipt_refs" in payload["blockers"]
    assert "receipt:gate_not_pass" in payload["blockers"]


def test_build_read_model_requires_sealed_evidence_when_manifest_requests_it(tmp_path):
    source = tmp_path / "evidence_manifest.json"
    output = tmp_path / "read_model.json"
    source.write_text(
        json.dumps(
            _manifest(
                sealed_evidence_required=True,
                rows=[
                    {
                        "delivery_status": "PASS",
                        "trust_status": "PASS",
                        "provider_token_cleanliness": "not_applicable",
                        "evidence_refs": ["docs/reports/evidence.json"],
                        "receipt_refs": ["docs/reports/receipt.json"],
                        "blockers": [],
                        "evidence_seal_status": "RETURN",
                        "evidence_hash_status": "PASS",
                    }
                ],
            )
        ),
        encoding="utf-8",
    )

    summary = build_read_model_from_evidence_manifest(input_path=source, output_path=output)
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert summary["status"] == "RETURN"
    assert payload["blockers"] == ["record_0:evidence_seal_not_pass"]
