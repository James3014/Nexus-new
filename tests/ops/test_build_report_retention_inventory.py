from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.ops.build_report_retention_inventory import (
    ReportArea,
    build_inventory,
    main,
    render_markdown,
    write_inventory,
)


def test_inventory_excludes_zero_trust_active_workstream(tmp_path):
    reports = tmp_path / "docs/reports"
    reports.mkdir(parents=True)
    (reports / "NEXUS_ZERO_TRUST_V2_REPLAY_MATRIX_2026-05-21.json").write_text("{}", encoding="utf-8")
    (reports / "NEXUS_HEEP_FLASH_NEXUS_EXECUTION_MATRIX_2026-05-20.json").write_text("{}", encoding="utf-8")

    inventory = build_inventory(reports_dir=reports, allow_default_policy_fallback=True)

    assert inventory["summary"]["rows"] == 1
    assert inventory["summary"]["excluded_active_workstream_count"] == 1
    assert inventory["rows"][0]["retention_class"] == "archive_candidate"
    assert inventory["rows"][0]["action"] == "no_move_no_delete_inventory_only"


def test_inventory_recursive_mode_discovers_nested_files_and_records_area(tmp_path):
    reports = tmp_path / "docs/reports"
    (reports / "archive/sf").mkdir(parents=True)
    (reports / "root-generated/2026-06-25").mkdir(parents=True)
    (reports / "assets").mkdir(parents=True)
    (reports / "local_model_armor_handoff_pack_v1").mkdir(parents=True)
    (reports / "3b-shadow-hardening").mkdir(parents=True)
    (reports / "root.md").write_text("root", encoding="utf-8")
    (reports / "archive/sf/historical.json").write_text("{}", encoding="utf-8")
    (reports / "root-generated/2026-06-25/result.jsonl").write_text("{}\n", encoding="utf-8")
    (reports / "assets/manifest.json").write_text("{}", encoding="utf-8")
    (reports / "local_model_armor_handoff_pack_v1/INDEX.md").write_text("handoff", encoding="utf-8")
    (reports / "3b-shadow-hardening/experiment.md").write_text("experiment", encoding="utf-8")

    inventory = build_inventory(reports_dir=reports, allow_default_policy_fallback=True)
    rows = {row["name"]: row for row in inventory["rows"]}

    assert inventory["summary"]["rows"] == 6
    assert rows["root.md"]["report_area"] == ReportArea.ROOT.value
    assert rows["historical.json"]["report_area"] == ReportArea.ARCHIVE.value
    assert rows["result.jsonl"]["report_area"] == ReportArea.GENERATED.value
    assert rows["manifest.json"]["report_area"] == ReportArea.ASSET.value
    assert rows["INDEX.md"]["report_area"] == ReportArea.HANDOFF.value
    assert rows["experiment.md"]["report_area"] == ReportArea.EXPERIMENT.value


def test_inventory_does_not_reclassify_archive_as_archive_candidate(tmp_path):
    reports = tmp_path / "docs/reports"
    target = reports / "archive/sf/NEXUS_HEEP_EXECUTION_MATRIX.json"
    target.parent.mkdir(parents=True)
    target.write_text("{}", encoding="utf-8")

    inventory = build_inventory(reports_dir=reports, allow_default_policy_fallback=True)

    assert inventory["rows"][0]["report_area"] == ReportArea.ARCHIVE.value
    assert inventory["rows"][0]["retention_class"] == "historical_preserved"


def test_inventory_marks_unknown_nested_domain_fail_closed(tmp_path):
    reports = tmp_path / "docs/reports"
    target = reports / "unexpected-domain/report.md"
    target.parent.mkdir(parents=True)
    target.write_text("unknown", encoding="utf-8")

    inventory = build_inventory(reports_dir=reports, allow_default_policy_fallback=True)

    assert inventory["rows"][0]["report_area"] == ReportArea.UNKNOWN.value
    assert inventory["rows"][0]["retention_class"] == "unknown_hold"
    assert inventory["rows"][0]["reason"] == "unknown_nested_report_area"


def test_inventory_area_mapping_is_loaded_from_manifest(tmp_path):
    reports = tmp_path / "docs/reports"
    target = reports / "custom-generated/result.json"
    target.parent.mkdir(parents=True)
    target.write_text("{}", encoding="utf-8")
    manifest = tmp_path / "report_area_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": "nexus.report_area_manifest.v1",
                "version": "v1",
                "directories": {"custom-generated": "generated"},
            }
        ),
        encoding="utf-8",
    )

    inventory = build_inventory(reports_dir=reports, area_manifest_path=manifest, allow_default_policy_fallback=True)

    assert inventory["rows"][0]["report_area"] == ReportArea.GENERATED.value
    assert inventory["rows"][0]["retention_class"] == "generated_evidence"


def test_inventory_rejects_invalid_area_manifest(tmp_path):
    reports = tmp_path / "docs/reports"
    reports.mkdir(parents=True)
    manifest = tmp_path / "report_area_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": "nexus.report_area_manifest.v1",
                "version": "v1",
                "directories": {"bad": "not-an-area"},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="not-an-area"):
        build_inventory(reports_dir=reports, area_manifest_path=manifest, allow_default_policy_fallback=True)


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

    inventory = build_inventory(reports_dir=reports, allow_default_policy_fallback=True)
    by_name = {row["name"]: row for row in inventory["rows"]}

    assert by_name[target.name]["retention_class"] == "keep_current_entrypoint"


def test_write_inventory_dry_run_does_not_write_outputs(tmp_path):
    reports = tmp_path / "docs/reports"
    reports.mkdir(parents=True)
    (reports / "NEXUS_HEEP_MAT_B_LIVE_REPORT_2026-05-20.json").write_text("{}", encoding="utf-8")
    json_output = tmp_path / "inventory.json"
    md_output = tmp_path / "inventory.md"

    summary = write_inventory(
        reports_dir=reports,
        json_output=json_output,
        md_output=md_output,
        dry_run=True,
        allow_default_policy_fallback=True,
    )

    assert summary["status"] == "PASS"
    assert summary["dry_run"] is True
    assert json_output.exists() is False
    assert md_output.exists() is False


def test_markdown_states_boundaries(tmp_path):
    reports = tmp_path / "docs/reports"
    reports.mkdir(parents=True)
    (reports / "NEXUS_HEEP_FLASH_NEXUS_EXECUTION_MATRIX_2026-05-20.json").write_text("{}", encoding="utf-8")

    text = render_markdown(build_inventory(reports_dir=reports, allow_default_policy_fallback=True))

    assert "Excludes active `ZERO_TRUST_V2` artifacts." in text
    assert "Do not use `git mv`" in text
    assert "Archive Candidates" in text
    assert "Report area counts:" in text


def test_main_default_outputs_remain_under_docs_reports(tmp_path, monkeypatch, capsys):
    reports = tmp_path / "docs/reports"
    reports.mkdir(parents=True)
    (reports / "NEXUS_HEEP_MAT_B_LIVE_REPORT_2026-05-20.json").write_text("{}", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert main(["--dry-run", "--allow-policy-fallback"]) == 0

    output = capsys.readouterr().out
    assert '"json_output": "docs/reports/NEXUS_REPORT_RETENTION_INVENTORY_2026-05-22.json"' in output
    assert '"md_output": "docs/reports/NEXUS_REPORT_RETENTION_PLAN_2026-05-22.md"' in output


def test_script_direct_invocation_supports_dry_run(tmp_path):
    reports = tmp_path / "docs/reports"
    reports.mkdir(parents=True)
    (reports / "report.md").write_text("report", encoding="utf-8")
    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "scripts/ops/build_report_retention_inventory.py"

    result = subprocess.run(
        [sys.executable, str(script), "--reports-dir", str(reports), "--allow-policy-fallback", "--dry-run"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["rows"] == 1
    assert payload["dry_run"] is True


def test_policy_manifest_loads_custom_keep_files(tmp_path):
    reports = tmp_path / "docs/reports"
    reports.mkdir(parents=True)
    (reports / "CUSTOM_KEPT_FILE.json").write_text("{}", encoding="utf-8")
    (reports / "other.json").write_text("{}", encoding="utf-8")
    manifest = tmp_path / "policy_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": "nexus.report_retention_policy_manifest.v1",
                "version": "v1",
                "active_workstream_patterns": [],
                "current_keep_files": ["CUSTOM_KEPT_FILE.json"],
                "raw_hints": [],
                "root_retention_keywords": {"human_entrypoint": []},
            }
        ),
        encoding="utf-8",
    )

    inventory = build_inventory(reports_dir=reports, policy_manifest_path=manifest)
    by_name = {row["name"]: row for row in inventory["rows"]}

    assert by_name["CUSTOM_KEPT_FILE.json"]["retention_class"] == "keep_current_entrypoint"
    assert by_name["other.json"]["retention_class"] == "unknown_hold"


def test_policy_manifest_rejects_invalid_schema(tmp_path):
    reports = tmp_path / "docs/reports"
    reports.mkdir(parents=True)
    manifest = tmp_path / "policy_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": "nexus.wrong.schema.v1",
                "version": "v1",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Invalid policy manifest schema"):
        build_inventory(reports_dir=reports, policy_manifest_path=manifest)


def test_policy_manifest_missing_fields_rejects(tmp_path):
    reports = tmp_path / "docs/reports"
    reports.mkdir(parents=True)
    manifest = tmp_path / "policy_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": "nexus.report_retention_policy_manifest.v1",
                "version": "v1",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="active_workstream_patterns"):
        build_inventory(reports_dir=reports, policy_manifest_path=manifest)


def test_policy_manifest_missing_file_fails_closed(tmp_path):
    reports = tmp_path / "docs/reports"
    reports.mkdir(parents=True)
    manifest = tmp_path / "nonexistent_manifest.json"

    with pytest.raises(FileNotFoundError, match="Policy manifest not found"):
        build_inventory(reports_dir=reports, policy_manifest_path=manifest)


def test_default_repository_execution_requires_policy_manifest(tmp_path, monkeypatch):
    reports = tmp_path / "docs/reports"
    reports.mkdir(parents=True)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(FileNotFoundError, match="Policy manifest required"):
        main(["--dry-run"])


def test_explicit_isolated_fallback_preserves_legacy_behavior(tmp_path):
    reports = tmp_path / "docs/reports"
    reports.mkdir(parents=True)
    (reports / "NEXUS_SF_FINAL_CURRENT_STATE_2026-05-20.md").write_text("{}", encoding="utf-8")

    inventory = build_inventory(reports_dir=reports, allow_default_policy_fallback=True)
    by_name = {row["name"]: row for row in inventory["rows"]}

    assert by_name["NEXUS_SF_FINAL_CURRENT_STATE_2026-05-20.md"]["retention_class"] == "keep_current_entrypoint"


def test_custom_active_pattern_changes_excluded_paths(tmp_path):
    reports = tmp_path / "docs/reports"
    reports.mkdir(parents=True)
    (reports / "CUSTOM_WORKSTREAM_file.json").write_text("{}", encoding="utf-8")
    (reports / "normal.json").write_text("{}", encoding="utf-8")
    manifest = tmp_path / "policy_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": "nexus.report_retention_policy_manifest.v1",
                "version": "v1",
                "active_workstream_patterns": ["CUSTOM_WORKSTREAM"],
                "current_keep_files": [],
                "raw_hints": [],
                "root_retention_keywords": {"human_entrypoint": ["SUMMARY"]},
            }
        ),
        encoding="utf-8",
    )

    inventory = build_inventory(reports_dir=reports, policy_manifest_path=manifest)

    assert inventory["summary"]["rows"] == 1
    assert inventory["summary"]["excluded_active_workstream_count"] == 1
    assert inventory["excluded_active_workstream_paths"][0].endswith("CUSTOM_WORKSTREAM_file.json")


def test_custom_raw_hint_changes_archive_classification(tmp_path):
    reports = tmp_path / "docs/reports"
    reports.mkdir(parents=True)
    (reports / "MY_CUSTOM_HINT_matrix.json").write_text("{}", encoding="utf-8")
    (reports / "plain.json").write_text("{}", encoding="utf-8")
    manifest = tmp_path / "policy_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": "nexus.report_retention_policy_manifest.v1",
                "version": "v1",
                "active_workstream_patterns": [],
                "current_keep_files": [],
                "raw_hints": ["MY_CUSTOM_HINT"],
                "root_retention_keywords": {"human_entrypoint": []},
            }
        ),
        encoding="utf-8",
    )

    inventory = build_inventory(reports_dir=reports, policy_manifest_path=manifest)
    by_name = {row["name"]: row for row in inventory["rows"]}

    assert by_name["MY_CUSTOM_HINT_matrix.json"]["retention_class"] == "archive_candidate"
    assert by_name["plain.json"]["retention_class"] == "unknown_hold"


def test_custom_human_keyword_changes_entrypoint_classification(tmp_path):
    reports = tmp_path / "docs/reports"
    reports.mkdir(parents=True)
    (reports / "MY_CUSTOM_SUMMARY.md").write_text("content", encoding="utf-8")
    (reports / "other.md").write_text("content", encoding="utf-8")
    manifest = tmp_path / "policy_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": "nexus.report_retention_policy_manifest.v1",
                "version": "v1",
                "active_workstream_patterns": [],
                "current_keep_files": [],
                "raw_hints": [],
                "root_retention_keywords": {"human_entrypoint": ["MY_CUSTOM_SUMMARY"]},
            }
        ),
        encoding="utf-8",
    )

    inventory = build_inventory(reports_dir=reports, policy_manifest_path=manifest)
    by_name = {row["name"]: row for row in inventory["rows"]}

    assert by_name["MY_CUSTOM_SUMMARY.md"]["retention_class"] == "keep_human_entrypoint"
    assert by_name["other.md"]["retention_class"] == "unknown_hold"


def test_policy_manifest_rejects_wrong_field_type(tmp_path):
    reports = tmp_path / "docs/reports"
    reports.mkdir(parents=True)
    manifest = tmp_path / "policy_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": "nexus.report_retention_policy_manifest.v1",
                "version": "v1",
                "active_workstream_patterns": "NOT_A_LIST",
                "current_keep_files": [],
                "raw_hints": [],
                "root_retention_keywords": {"human_entrypoint": ["SUMMARY"]},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="active_workstream_patterns must be a"):
        build_inventory(reports_dir=reports, policy_manifest_path=manifest)
