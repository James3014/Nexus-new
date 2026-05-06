import importlib
import json


def test_wiki_coverage_audit_ignores_missing_key_paths(tmp_path, monkeypatch):
    audit = importlib.import_module("scripts.ops.wiki_coverage_audit")

    repo = tmp_path / "repo"
    vault = repo / "nexus_wiki_vault"
    src = repo / "src"
    reports = repo / ".nexus" / "reports"
    src.mkdir(parents=True)
    vault.mkdir(parents=True)
    (src / "present.py").write_text("print('ok')\n", encoding="utf-8")
    (vault / "Present.md").write_text(
        "---\nsource_of_truth: src/present.py\n---\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(audit, "REPO_ROOT", repo)
    monkeypatch.setattr(audit, "VAULT_ROOT", vault)
    monkeypatch.setattr(audit, "REPORT_PATH", reports / "wiki_coverage_report.json")
    monkeypatch.setattr(
        audit,
        "KEYPATH_REPORT_PATH",
        reports / "wiki_keypath_coverage_report.json",
    )
    monkeypatch.setattr(audit, "TARGET_DIRS", ["src"])
    monkeypatch.setattr(audit, "KEY_PATHS", ["src/present.py", "src/missing.py"])

    audit.run_audit()

    keypath_report = json.loads((reports / "wiki_keypath_coverage_report.json").read_text())
    assert keypath_report["keypath_status"] == "PASS"
    assert keypath_report["keypath_uncovered"] == []
    assert keypath_report["keypath_missing"] == ["src/missing.py"]


def test_wiki_capability_required_labels_are_complete():
    audit = importlib.import_module("scripts.ops.wiki_capability_coverage_audit")

    result = audit.audit_capabilities()

    missing = {
        domain: data["labels_missing"]
        for domain, data in result["results"].items()
        if data["labels_missing"]
    }
    assert missing == {}


def test_wiki_slo_dashboard_reads_nested_coverage_report():
    dashboard = importlib.import_module("scripts.ops.wiki_slo_dashboard")

    snapshot = dashboard._coverage_snapshot(
        {
            "summary": {
                "coverage_ratio": "39.74%",
                "keypath_coverage_ratio": "100.00%",
            }
        }
    )

    assert snapshot == {"global": 39.74, "keypath": 100.0}
