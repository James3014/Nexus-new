from __future__ import annotations

import json

from scripts.ops.build_publication_readiness_gate import build_gate_from_files, main


def _benchmark() -> dict[str, object]:
    return {
        "same_model": True,
        "paired_comparison": True,
        "taskset_frozen": True,
        "hidden_verifier_mode": True,
        "public_claim_gate_pass": True,
        "wearing_evidence_valid": True,
        "evidence_bundle_sealed": True,
        "evidence_hash_valid": True,
        "completion_envelope_status": "PASS",
        "eligible_without_n": 1,
        "eligible_with_n": 1,
        "infra_invalid_without_n": 0,
        "infra_invalid_with_n": 0,
        "trust_mismatch_with_rate": 0,
        "provider_token_cleanliness": "measured",
    }


def _read_model() -> dict[str, object]:
    return {
        "status": "PASS",
        "claim_class": "PUBLIC_READY",
        "provider_token_cleanliness": "measured",
        "evidence_bundle_refs": ["docs/reports/evidence.json"],
        "receipt_refs": ["docs/reports/receipt.json"],
        "records": [{"evidence_seal_status": "PASS", "evidence_hash_status": "PASS"}],
        "gates": [
            {"name": "delivery", "status": "PASS"},
            {"name": "trust", "status": "PASS"},
            {"name": "artifact", "status": "PASS"},
            {"name": "receipt", "status": "PASS"},
            {"name": "claim", "status": "PASS"},
        ],
    }


def test_build_publication_readiness_gate_from_files(tmp_path) -> None:
    benchmark = tmp_path / "benchmark.json"
    read_model = tmp_path / "read_model.json"
    output = tmp_path / "gate.json"
    benchmark.write_text(json.dumps(_benchmark()), encoding="utf-8")
    read_model.write_text(json.dumps(_read_model()), encoding="utf-8")

    summary = build_gate_from_files(benchmark_summary_path=benchmark, read_model_path=read_model, output_path=output)

    assert summary["status"] == "PASS"
    assert summary["publication_ready"] is True
    assert output.exists() is True


def test_publication_readiness_cli_returns_nonzero_when_gate_blocks(tmp_path, capsys) -> None:
    benchmark = tmp_path / "benchmark.json"
    read_model = tmp_path / "read_model.json"
    benchmark.write_text(json.dumps({**_benchmark(), "same_model": False}), encoding="utf-8")
    read_model.write_text(json.dumps(_read_model()), encoding="utf-8")

    rc = main(["--benchmark-summary", str(benchmark), "--read-model", str(read_model), "--dry-run"])
    payload = json.loads(capsys.readouterr().out)

    assert rc == 1
    assert payload["status"] == "RETURN"
    assert payload["dry_run"] is True
