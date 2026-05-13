from __future__ import annotations

import json

from click.testing import CliRunner

from nexus.engine.capability_coverage_gap import build_capability_coverage_gap_report, write_capability_coverage_gap_report
from scripts.engine import nexus_cli
from scripts.engine.nexus_cli import nexus


def test_capability_coverage_gap_report_marks_reserved_and_pending(tmp_path):
    report = build_capability_coverage_gap_report()

    assert report["schema_version"] == "nexus_capability_coverage_gap_v1"
    assert report["unruled_count"] == 0
    assert {item["capability"] for item in report["reserved_capabilities"]} == {"autonomic_router", "learn_scheduler"}
    assert report["pending_executor_capabilities"] == []

    path = write_capability_coverage_gap_report(tmp_path / "gap.json")
    assert json.loads(path.read_text(encoding="utf-8"))["unruled_count"] == 0


def test_capability_coverage_gap_cli_writes_report(tmp_path, monkeypatch):
    monkeypatch.setattr(nexus_cli, "repo_root", tmp_path)
    report = tmp_path / ".nexus" / "reports" / "capability_coverage_gap.json"

    result = CliRunner().invoke(
        nexus,
        ["nexus", "capability:coverage-gap", "--report-file", str(report), "--output-json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["report_path"] == str(report)
    assert report.exists()
