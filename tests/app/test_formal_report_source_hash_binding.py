"""#1869: the formal_report producer binds its gate to the sha256 of the report bytes it verified."""

from __future__ import annotations

import hashlib
from pathlib import Path

from nexus.app.research_semantic_runtime import augment_semantic_runtime_capabilities
from nexus.engine.capability_receipt_adapters import RECEIPT_ADAPTERS


def _run(tmp_path: Path, *, artifact_verified: bool) -> dict:
    trace: dict = {
        "capabilities": {
            "artifact_refs": ["a"],
            "artifact_gate_passed": True,
            "judge_panel_report_path": "j",
            "judge_panel_gate_passed": True,
            "judge_panel_votes": [{"judge": "x", "ranking": ["A"]}],
        }
    }
    augment_semantic_runtime_capabilities(
        repo_root=tmp_path,
        task_id="t1",
        task_desc="fix",
        task_type="repair",
        target_file=None,
        receipt_slug="slug1869",
        selected_capabilities={"formal_report"},
        nexus_usage_trace=trace,
        route={},
        asi_ledger=[],
        plateau={},
        artifact_verified=artifact_verified,
        normalized_success_criteria="pytest",
    )
    return trace["capabilities"]


def test_formal_report_producer_emits_hash_of_written_bytes_and_gate_passes(tmp_path: Path) -> None:
    caps = _run(tmp_path, artifact_verified=True)
    written = (tmp_path / caps["formal_report_path"]).read_bytes()
    assert caps["source_hash"] == "sha256:" + hashlib.sha256(written).hexdigest()
    assert caps["verifier_status"] == "pass"
    receipt = RECEIPT_ADAPTERS["formal_report"].build(claim_verified=True, payload=caps)
    assert receipt.gate_passed is True
    assert receipt.outcome_contributed is False


def test_formal_report_producer_unverified_artifact_stays_false(tmp_path: Path) -> None:
    caps = _run(tmp_path, artifact_verified=False)
    assert caps["formal_report_gate_passed"] is False
    receipt = RECEIPT_ADAPTERS["formal_report"].build(claim_verified=True, payload=caps)
    assert receipt.gate_passed is False
