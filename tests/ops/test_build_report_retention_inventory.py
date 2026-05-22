from __future__ import annotations

from scripts.ops.build_report_retention_inventory import build_inventory, main, render_markdown, write_inventory


def test_inventory_excludes_zero_trust_active_workstream(tmp_path):
    reports = tmp_path / "docs/reports"
    reports.mkdir(parents=True)
    (reports / "NEXUS_ZERO_TRUST_V2_REPLAY_MATRIX_2026-05-21.json").write_text("{}", encoding="utf-8")
    (reports / "NEXUS_HEEP_FLASH_NEXUS_EXECUTION_MATRIX_2026-05-20.json").write_text("{}", encoding="utf-8")

    inventory = build_inventory(reports_dir=reports)

    assert inventory["summary"]["rows"] == 1
    assert inventory["summary"]["excluded_active_workstream_count"] == 1
    assert inventory["rows"][0]["retention_class"] == "archive_candidate"
    assert inventory["rows"][0]["action"] == "no_move_no_delete_inventory_only"


def test_inventory_keeps_manifest_referenced_sf_current_files(tmp_path):
    reports = tmp_path / "docs/reports"
    reports.mkdir(parents=True)
    manifest = reports / "NEXUS_SF_WORKSPACE_RETENTION_CURRENT_MANIFEST_2026-05-20.json"
    manifest.write_text(
        '{"keep_artifacts":["docs/reports/NEXUS_SF_SYSTEMATIC_FINALIZATION_V32_2026-05-19.json"]}',
        encoding="utf-8",
    )
    target = reports / "NEXUS_SF_SYSTEMATIC_FINALIZATION_V32_2026-05-19.json"
    target.write_text("{}", encoding="utf-8")

    inventory = build_inventory(reports_dir=reports)
    by_name = {row["name"]: row for row in inventory["rows"]}

    assert by_name[target.name]["retention_class"] == "keep_current_entrypoint"


def test_write_inventory_dry_run_does_not_write_outputs(tmp_path):
    reports = tmp_path / "docs/reports"
    reports.mkdir(parents=True)
    (reports / "NEXUS_HEEP_MAT_B_LIVE_REPORT_2026-05-20.json").write_text("{}", encoding="utf-8")
    json_output = tmp_path / "inventory.json"
    md_output = tmp_path / "inventory.md"

    summary = write_inventory(reports_dir=reports, json_output=json_output, md_output=md_output, dry_run=True)

    assert summary["status"] == "PASS"
    assert summary["dry_run"] is True
    assert json_output.exists() is False
    assert md_output.exists() is False


def test_markdown_states_boundaries(tmp_path):
    reports = tmp_path / "docs/reports"
    reports.mkdir(parents=True)
    (reports / "NEXUS_HEEP_FLASH_NEXUS_EXECUTION_MATRIX_2026-05-20.json").write_text("{}", encoding="utf-8")

    text = render_markdown(build_inventory(reports_dir=reports))

    assert "Excludes active `ZERO_TRUST_V2` artifacts." in text
    assert "Do not use `git mv`" in text
    assert "Archive Candidates" in text


def test_main_default_outputs_remain_under_docs_reports(tmp_path, monkeypatch, capsys):
    reports = tmp_path / "docs/reports"
    reports.mkdir(parents=True)
    (reports / "NEXUS_HEEP_MAT_B_LIVE_REPORT_2026-05-20.json").write_text("{}", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert main(["--dry-run"]) == 0

    output = capsys.readouterr().out
    assert '"json_output": "docs/reports/NEXUS_REPORT_RETENTION_INVENTORY_2026-05-22.json"' in output
    assert '"md_output": "docs/reports/NEXUS_REPORT_RETENTION_PLAN_2026-05-22.md"' in output
