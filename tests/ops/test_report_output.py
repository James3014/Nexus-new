from __future__ import annotations

from pathlib import Path

from scripts.ops.report_output import resolve_run_report_output


def test_resolve_run_report_output_places_default_under_safe_run_directory(tmp_path: Path) -> None:
    default = Path("docs/reports/NEXUS_OPT_ROUTE_DAG_PREGATE_2026-05-20.json")

    output = resolve_run_report_output(default, output_dir=tmp_path, run_id="SF V16 / smoke")

    assert output == tmp_path / "SF-V16-smoke" / default.name


def test_resolve_run_report_output_keeps_explicit_output() -> None:
    explicit = Path("custom.json")

    assert resolve_run_report_output(Path("default.json"), output=explicit, run_id="ignored") == explicit
