from __future__ import annotations

import json
from pathlib import Path

from scripts.ops.hallucination_guard_drift import audit_drift


def test_hallucination_guard_drift_passes_repository_alignment():
    audit = audit_drift()

    assert audit.passed is True
    assert "logic_mismatch" in audit.schema_checks
    assert "verified_claim_without_evidence" in audit.runtime_checks


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

    audit = audit_drift(schema_path=schema_path, alignment_doc=doc_path)

    assert audit.passed is False
    assert {"reason": "schema_check_missing_runtime_method", "check": "ghost_check"} in audit.failures
