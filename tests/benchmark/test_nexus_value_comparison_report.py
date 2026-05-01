from __future__ import annotations

import json
from pathlib import Path

from scripts.bench.nexus_value_comparison_report import main, render_report, summarize_run


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def test_summarize_run_prefers_markdown_gate_and_keeps_infra_boundary(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write_jsonl(
        run_dir / "without_nexus_1.jsonl",
        [
            {"task_id": "a", "trial_index": 1, "semantic_status": "VERIFIED", "run_eligible": True, "wall_duration_sec": 10, "model_calls": 1, "total_tokens": 100},
            {"task_id": "b", "trial_index": 1, "semantic_status": "UNVERIFIED", "run_eligible": False, "infra_invalid_reason": "auth_failed"},
        ],
    )
    _write_jsonl(
        run_dir / "with_nexus_1.jsonl",
        [
            {"task_id": "a", "trial_index": 1, "semantic_status": "VERIFIED", "run_eligible": True, "wall_duration_sec": 20, "model_calls": 1, "total_tokens": 120},
            {"task_id": "b", "trial_index": 1, "semantic_status": "VERIFIED", "run_eligible": True, "wall_duration_sec": 22, "model_calls": 1, "total_tokens": 140},
        ],
    )
    (run_dir / "gemini_nexus_report_1.md").write_text("- Public claim gate: FAIL\n- Public claim gate failures: run_eligibility_incomplete:1\n", encoding="utf-8")
    (run_dir / "evidence_bundle.json").write_text(
        json.dumps({"schema": "nexus_public_benchmark_evidence_bundle_v2", "public_claim_gate": {"verdict": "PASS", "failures": []}}),
        encoding="utf-8",
    )

    summary = summarize_run("GPT-5.5", run_dir, scope="2 rows", claim_status="observation")
    report = render_report([summary])

    assert summary.bare.eligible == 1
    assert summary.bare.verified == 1
    assert summary.nexus.verified == 2
    assert "markdown FAIL; bundle PASS" in summary.gate_status
    assert "markdown failures: run_eligibility_incomplete:1" in report
    assert "GPT-5.5" in report


def test_main_accepts_claim_boundary_notes(tmp_path: Path, monkeypatch) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write_jsonl(
        run_dir / "without_nexus_1.jsonl",
        [{"task_id": "a", "trial_index": 1, "semantic_status": "UNVERIFIED", "run_eligible": True}],
    )
    _write_jsonl(
        run_dir / "with_nexus_1.jsonl",
        [{"task_id": "a", "trial_index": 1, "semantic_status": "VERIFIED", "run_eligible": True}],
    )
    output = tmp_path / "out.md"
    monkeypatch.setattr(
        "sys.argv",
        [
            "report",
            "--run",
            f"GPT-5.5={run_dir}=1x1=performance candidate",
            "--note",
            "GPT-5.5=capability gate FAIL",
            "--output",
            str(output),
        ],
    )

    assert main() == 0
    assert "capability gate FAIL" in output.read_text(encoding="utf-8")
