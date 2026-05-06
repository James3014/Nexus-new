from __future__ import annotations

import json
from pathlib import Path

from nexus.core.hallucination_guard import HallucinationGuard
from scripts.ops.hallucination_guard_drift import audit_drift


def test_hallucination_guard_drift_passes_repository_alignment():
    audit = audit_drift()

    assert audit.passed is True
    assert "logic_mismatch" in audit.schema_checks
    assert "verified_claim_without_evidence" in audit.runtime_checks
    assert audit.runtime_probes["logic_mismatch_hard_rejects"] is True
    assert audit.runtime_probes["logic_mismatch_allows_match"] is True


def test_hallucination_guard_drift_fails_schema_without_runtime_backing(tmp_path: Path):
    schema = {
        "metrics": {
            "ghost_metric": {
                "weight": 9,
                "check": "ghost_check",
            }
        },
        "thresholds": {"VERIFIED": 2, "PARTIAL": 5, "REJECTED": 6},
    }
    schema_path = tmp_path / "hallucination_index_v1.json"
    doc_path = tmp_path / "alignment.md"
    schema_path.write_text(json.dumps(schema), encoding="utf-8")
    doc_path.write_text("# Alignment\n", encoding="utf-8")

    spec_path = tmp_path / "scoring.md"
    spec_path.write_text("| **Evidence Gap** | x | **-7.0** | YES |\n", encoding="utf-8")

    audit = audit_drift(schema_path=schema_path, alignment_doc=doc_path, scoring_spec=spec_path)

    assert audit.passed is False
    assert {"reason": "schema_check_missing_runtime_method", "check": "ghost_check"} in audit.failures


def test_hallucination_guard_drift_fails_when_runtime_probe_is_soft(tmp_path: Path):
    schema_path = Path("nexus/schemas/hallucination_index_v1.json")
    doc_path = tmp_path / "alignment.md"
    doc_path.write_text("# Alignment\nlogic mismatch 邏輯 mismatch\n", encoding="utf-8")

    class SoftLogicGuard(HallucinationGuard):
        def _check_logic_mismatch(self) -> bool:
            return False

    audit = audit_drift(
        schema_path=schema_path,
        alignment_doc=doc_path,
        guard_factory=lambda schema_path: SoftLogicGuard(schema_path=schema_path),
    )

    assert audit.passed is False
    assert {"reason": "runtime_probe_failed", "probe": "logic_mismatch_hard_rejects"} in audit.failures


def test_drift_fails_when_scoring_spec_logic_mismatch_hard_block_disagrees(tmp_path: Path):
    spec_path = tmp_path / "scoring.md"
    spec_path.write_text(
        "| **Evidence Gap** | x | **-7.0** | YES |\n"
        "| **Benchmark Fail** | x | **-9.0** | YES |\n"
        "| **Logic Mismatch** | x | **-8.0** | NO |\n"
        "| **Verified Claim** | x | **-8.0** | YES |\n",
        encoding="utf-8",
    )

    audit = audit_drift(scoring_spec=spec_path)

    assert audit.passed is False
    assert any(
        item["reason"] == "scoring_spec_hard_block_mismatch" and item["rule_id"] == "logic_mismatch"
        for item in audit.failures
    )


def test_drift_fails_when_scoring_spec_weight_disagrees_with_schema(tmp_path: Path):
    spec_path = tmp_path / "scoring.md"
    spec_path.write_text(
        "| **Evidence Gap** | x | **-7.0** | YES |\n"
        "| **Benchmark Fail** | x | **-9.0** | YES |\n"
        "| **Logic Mismatch** | x | **-4.0** | YES |\n"
        "| **Verified Claim** | x | **-8.0** | YES |\n",
        encoding="utf-8",
    )

    audit = audit_drift(scoring_spec=spec_path)

    assert audit.passed is False
    assert any(
        item["reason"] == "scoring_spec_weight_mismatch" and item["rule_id"] == "logic_mismatch"
        for item in audit.failures
    )
