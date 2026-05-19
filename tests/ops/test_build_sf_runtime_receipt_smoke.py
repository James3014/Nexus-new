from __future__ import annotations

from scripts.ops.build_sf_runtime_receipt_smoke import _report_path


def test_report_path_falls_back_to_sf_archive(tmp_path):
    report = "NEXUS_SKILL_STATUS_2026-05-15.json"
    archived = tmp_path / "docs/reports/archive/sf/2026-05-15" / report
    archived.parent.mkdir(parents=True)
    archived.write_text("{}", encoding="utf-8")

    assert _report_path(tmp_path, report, date="2026-05-15") == archived
