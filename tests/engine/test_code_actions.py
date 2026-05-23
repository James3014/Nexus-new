from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

import scripts.engine.nexus_cli as cli_mod
from scripts.engine.commands.code_actions import (
    CodeActionResult,
    render_code_context,
    render_code_impact,
    run_code_context,
    run_code_impact,
    run_code_scan,
)


class FakeCodeIntelResult:
    def __init__(self, payload):
        self._payload = payload

    def to_dict(self):
        return dict(self._payload)


def test_run_code_impact_writes_report_and_evidence_path(tmp_path: Path):
    calls = []

    def fake_analyze(root: Path, changed_files: list[str], *, index_path: str | None):
        calls.append((root, changed_files, index_path))
        return FakeCodeIntelResult({"impacted_files": ["b.py"], "risk_score": 0.75, "evidence_paths": []})

    result = run_code_impact(
        tmp_path,
        files_text="a.py, , b.py",
        index_path="graph.json",
        report_file="reports/impact.json",
        analyze_impact=fake_analyze,
    )

    assert calls == [(tmp_path, ["a.py", "b.py"], "graph.json")]
    assert result.report_path == tmp_path / "reports/impact.json"
    assert result.payload["report_path"] == str(result.report_path)
    assert result.payload["evidence_paths"] == [str(result.report_path)]
    assert json.loads(result.report_path.read_text(encoding="utf-8")) == result.payload
    assert render_code_impact(result) == [
        "Code impact: 1 impacted files, risk=0.75",
        f"Report: {result.report_path}",
    ]


def test_run_code_scan_writes_report_without_injecting_report_path(tmp_path: Path):
    def fake_scan(root: Path, *, index_path: str | None):
        assert root == tmp_path
        assert index_path == "index.json"
        return FakeCodeIntelResult({"nodes_count": 3, "edges_count": 2, "index_path": "index.json"})

    result = run_code_scan(
        tmp_path,
        index_path="index.json",
        report_file=tmp_path / "scan.json",
        scan_codebase=fake_scan,
    )

    assert result.payload == {"nodes_count": 3, "edges_count": 2, "index_path": "index.json"}
    assert json.loads(result.report_path.read_text(encoding="utf-8")) == result.payload


def test_run_code_context_and_render_missing_symbol(tmp_path: Path):
    def fake_context(root: Path, symbol: str, *, index_path: str | None):
        assert root == tmp_path
        assert symbol == "missing_symbol"
        assert index_path is None
        return FakeCodeIntelResult({"found": False, "reason": "not_indexed"})

    result = run_code_context(
        tmp_path,
        symbol="missing_symbol",
        index_path=None,
        report_file=None,
        context_for_symbol=fake_context,
    )

    assert result.report_path == tmp_path / ".nexus" / "reports" / "codeintel" / "context.json"
    assert render_code_context(result, symbol="missing_symbol") == [
        "Code context: missing_symbol missing:not_indexed",
        f"Report: {result.report_path}",
    ]


def test_code_impact_cli_uses_action_result(monkeypatch, tmp_path: Path):
    def fake_run_code_impact(root: Path, **kwargs):
        assert root == tmp_path
        assert kwargs["files_text"] == "a.py"
        return CodeActionResult(
            payload={"impacted_files": ["b.py"], "risk_score": 0.5},
            report_path=tmp_path / "impact.json",
        )

    monkeypatch.setattr(cli_mod, "repo_root", tmp_path)
    monkeypatch.setattr(cli_mod, "run_code_impact", fake_run_code_impact)

    result = CliRunner().invoke(cli_mod.nexus, ["nexus", "code", "impact", "--files", "a.py"])

    assert result.exit_code == 0
    assert "Code impact: 1 impacted files, risk=0.5" in result.output
