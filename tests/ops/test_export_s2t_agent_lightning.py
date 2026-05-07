from __future__ import annotations

import json
from pathlib import Path

from scripts.ops.export_s2t_agent_lightning import export_s2t_trace_file, main


def _write_trace(path: Path) -> None:
    event = {
        "schema_version": "s2t.v1",
        "task_id": "task-1",
        "run_id": "run-1",
        "model": "gemini-3-flash-preview",
        "mode": "shadow",
        "phase": "R",
        "risk_tier": "high",
        "candidate_set_id": "candset-1",
        "candidates": [
            {
                "candidate_id": "A",
                "source": "repair_pass",
                "content_ref": ".nexus/reports/s2t/candidates/A.json",
                "claimed_outcome": "untested patch",
                "static_score": 0.8,
                "selector_score": 0.95,
                "verifier_result": "fail",
                "evidence_refs": [],
                "risk_flags": ["missing_test_evidence"],
            },
            {
                "candidate_id": "B",
                "source": "repair_pass",
                "content_ref": ".nexus/reports/s2t/candidates/B.json",
                "claimed_outcome": "verified patch",
                "static_score": 0.7,
                "selector_score": 0.75,
                "verifier_result": "pass",
                "evidence_refs": ["tests/test_target.py"],
                "risk_flags": [],
            },
        ],
        "selected_candidate_id": "B",
        "selection_reason_codes": ["has_empirical_test_evidence"],
        "verifier_name": "pytest",
        "verifier_result": "pass",
        "verifier_evidence_ref": ".nexus/reports/pytest.json",
        "secret_values": {"api_token": "secret"},
        "private_paths": ["/Users/jameschen/private.txt"],
    }
    path.write_text(json.dumps(event) + "\n", encoding="utf-8")


def test_export_s2t_trace_file_writes_preference_json(tmp_path: Path) -> None:
    trace = tmp_path / "trace.jsonl"
    output = tmp_path / "agent_lightning.json"
    _write_trace(trace)

    summary = export_s2t_trace_file(trace, output, dry_run=False)

    exported = json.loads(output.read_text(encoding="utf-8"))
    assert summary["source_rows"] == 1
    assert summary["preference_pairs"] == 1
    assert exported["pairs"][0]["chosen_candidate_id"] == "B"
    assert exported["redacted_source_rows"][0]["secret_values"] == {}
    assert exported["redacted_source_rows"][0]["private_paths"] == ["<redacted-path>"]


def test_export_s2t_trace_file_dry_run_does_not_write(tmp_path: Path) -> None:
    trace = tmp_path / "trace.jsonl"
    output = tmp_path / "agent_lightning.json"
    _write_trace(trace)

    summary = export_s2t_trace_file(trace, output, dry_run=True)

    assert summary["dry_run"] is True
    assert summary["preference_pairs"] == 1
    assert not output.exists()


def test_export_s2t_trace_file_writes_v2_with_v1_compat(tmp_path: Path) -> None:
    trace = tmp_path / "trace.jsonl"
    output = tmp_path / "model_training.json"
    _write_trace(trace)

    summary = export_s2t_trace_file(trace, output, dry_run=False, export_format="v2")

    exported = json.loads(output.read_text(encoding="utf-8"))
    assert summary["format"] == "v2"
    assert summary["preference_pairs"] == 1
    assert exported["schema_version"] == "nexus_model_training_export.v2"
    assert exported["compat"]["agent_lightning_preferences_v1"]["pair_count"] == 1
    assert exported["redacted_source_rows"][0]["secret_values"] == {}


def test_export_s2t_main_returns_nonzero_for_missing_input(tmp_path: Path) -> None:
    rc = main(["--input", str(tmp_path / "missing.jsonl"), "--output", str(tmp_path / "out.json")])

    assert rc == 1
