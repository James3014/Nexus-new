from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

import scripts.engine.nexus_cli as cli_mod
from scripts.engine.commands.bench_actions import (
    EffortRoiRow,
    get_effort_roi_report,
    render_effort_roi_report,
)
from scripts.engine.commands.exception_translation import NexusCliActionError


class FakeRunner:
    def __init__(self, report):
        self._report = report

    def generate_effort_roi_report(self):
        return self._report


def test_get_effort_roi_report_normalizes_runner_mapping(tmp_path: Path):
    calls: list[Path] = []

    def runner_factory(root: Path) -> FakeRunner:
        calls.append(root)
        return FakeRunner(
            {
                "low": {"success_rate": "0.875", "avg_duration_sec": "1.25", "count": "4"},
                "high": {"success_rate": 1.0, "avg_duration_sec": 9, "count": 2},
            }
        )

    report = get_effort_roi_report(tmp_path, runner_factory=runner_factory)

    assert calls == [tmp_path]
    assert report == {
        "low": EffortRoiRow(success_rate=0.875, avg_duration_sec=1.25, count=4),
        "high": EffortRoiRow(success_rate=1.0, avg_duration_sec=9.0, count=2),
    }


def test_render_effort_roi_report_preserves_cli_output_schema():
    lines = render_effort_roi_report(
        {
            "low": EffortRoiRow(success_rate=0.875, avg_duration_sec=1.25, count=4),
            "high": EffortRoiRow(success_rate=1.0, avg_duration_sec=9.0, count=2),
        }
    )

    assert lines == [
        "📈 [Nexus Effort ROI Report]",
        "",
        "[LOW]",
        "  Success Rate: 87.50%",
        "  Avg Duration: 1.2s",
        "  Count       : 4",
        "",
        "[HIGH]",
        "  Success Rate: 100.00%",
        "  Avg Duration: 9.0s",
        "  Count       : 2",
    ]


def test_bench_effort_cli_uses_action_result(monkeypatch, tmp_path: Path):
    def fake_get_effort_roi_report(root: Path):
        assert root == tmp_path
        return {
            "low": EffortRoiRow(success_rate=0.875, avg_duration_sec=1.25, count=4),
        }

    monkeypatch.setattr(cli_mod, "repo_root", tmp_path)
    monkeypatch.setattr(cli_mod, "get_effort_roi_report", fake_get_effort_roi_report)

    result = CliRunner().invoke(cli_mod.nexus, ["nexus", "bench", "effort"])

    assert result.exit_code == 0
    assert "[LOW]" in result.output
    assert "Success Rate: 87.50%" in result.output
    assert "Avg Duration: 1.2s" in result.output


def test_bench_effort_cli_translates_action_errors(monkeypatch, tmp_path: Path):
    def fake_get_effort_roi_report(root: Path):
        raise NexusCliActionError("bench effort unavailable", exit_code=6)

    monkeypatch.setattr(cli_mod, "repo_root", tmp_path)
    monkeypatch.setattr(cli_mod, "get_effort_roi_report", fake_get_effort_roi_report)

    result = CliRunner().invoke(cli_mod.nexus, ["nexus", "bench", "effort"])

    assert result.exit_code == 6
    assert "Error: bench effort unavailable" in result.output
