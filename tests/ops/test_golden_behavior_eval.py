from __future__ import annotations

import json
import sys

from scripts.ops import run_golden_behavior_eval as evaluator


def test_validate_corpus_allows_growth_beyond_previous_ceiling(monkeypatch):
    cases = list(evaluator.CASES)
    monkeypatch.setattr(evaluator, "CASES", tuple(cases + cases[:1] * 100))

    errors = evaluator.validate_corpus()

    assert not any(error.startswith("case_count_out_of_range") for error in errors)
    assert "duplicate_case_id" in errors


def test_collect_witness_fails_closed_for_stale_exact_node():
    evidence = evaluator.collect_witness(
        "tests/contracts/test_canonical_execution.py::test_this_exact_node_does_not_exist"
    )

    assert evidence["collection_status"] == "collection_failed"
    assert evidence["collection_exit_code"] != 0
    assert evidence["collection_detail"]


def test_collect_witness_does_not_execute_test_body(tmp_path):
    marker = tmp_path / "executed.txt"
    test_file = tmp_path / "test_collect_only_probe.py"
    test_file.write_text(
        "from pathlib import Path\n"
        f"MARKER = Path({str(marker)!r})\n"
        "def test_body():\n"
        "    MARKER.write_text('executed', encoding='utf-8')\n",
        encoding="utf-8",
    )

    evidence = evaluator.collect_witness(f"{test_file}::test_body")

    assert evidence == {"collection_status": "collected", "collection_exit_code": 0}
    assert not marker.exists()


def test_validate_only_report_binds_provenance_and_case_witness_map(tmp_path, monkeypatch):
    report_path = tmp_path / "golden.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_golden_behavior_eval.py",
            "--validate-only",
            "--case",
            "GB-001",
            "--json-report",
            str(report_path),
        ],
    )

    assert evaluator.main() == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert report["schema"] == "nexus.golden_behavior_eval.v1"
    assert len(report["source_revision"]) == 40
    assert len(report["source_tree"]) == 40
    assert isinstance(report["workspace_dirty"], bool)
    assert len(report["corpus_identity"]) == 64
    assert len(report["evaluator_identity"]) == 64
    assert len(report["dependency_lock_identity"]) == 64
    assert report["python_version"]
    assert report["pytest_version"]
    assert report["validation_errors"] == []
    assert report["selected_case_count"] == 1
    assert report["case_evidence"][0]["case_id"] == "GB-001"
    witness = report["case_evidence"][0]["witnesses"][0]
    assert witness["collection_status"] == "collected"
    assert witness["execution_status"] == "not_executed_validate_only"
