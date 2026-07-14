import importlib
import json
from pathlib import Path


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


def test_wiki_global_coverage_meets_closure_threshold():
    audit = importlib.import_module("scripts.ops.wiki_coverage_audit")

    files = audit.get_code_files()
    mentions = audit.get_covered_files_from_wiki()
    basename_to_rels = {}
    for path in files:
        basename_to_rels.setdefault(path.rsplit("/", 1)[-1], []).append(path)

    covered_count = 0
    for path in files:
        basename = path.rsplit("/", 1)[-1]
        if path in mentions:
            covered_count += 1
            continue
        if basename in mentions and len(basename_to_rels.get(basename, [])) == 1:
            covered_count += 1
            continue
        if any(match == path or match.endswith(path) or path.endswith(match) for match in mentions):
            covered_count += 1

    assert covered_count / len(files) >= 0.85


def _authority_row(label: str, page: str) -> dict:
    return {
        "label": label,
        "authority_page": page,
        "authority_classification": "active",
        "source_evidence": {
            "kind": "code_backed",
            "source_path": "scripts/ops/ci_gate.py",
        },
    }


def test_required_authority_manifest_passes_live_phase3_inventory():
    audit = importlib.import_module("scripts.ops.wiki_capability_coverage_audit")
    result = audit.audit_capabilities(stale_days=45)

    assert result["authority_checks"]["status"] == "PASS"
    assert result["authority_checks"]["required_count"] == 7
    assert result["authority_checks"]["resolved_count"] == 7
    assert all(not data["labels_missing"] for data in result["results"].values())
    assert all(not data["pages_missing"] for data in result["results"].values())


def test_duplicate_authority_label_fails_closed(tmp_path: Path, monkeypatch):
    audit = importlib.import_module("scripts.ops.wiki_capability_coverage_audit")
    repo = tmp_path / "repo"
    vault = repo / "nexus_wiki_vault"
    (repo / "scripts" / "ops").mkdir(parents=True)
    (repo / "scripts" / "ops" / "ci_gate.py").write_text("def main():\n    return 0\n")
    first = vault / "01_System" / "First.md"
    second = vault / "01_System" / "Second.md"
    first.parent.mkdir(parents=True)
    first.write_text("---\nstatus: active\nowner: test\n---\n[Code: scripts/ops/ci_gate.py]\n")
    second.write_text("---\nstatus: active\nowner: test\n---\n[Code: scripts/ops/ci_gate.py]\n")
    monkeypatch.setattr(audit, "REPO_ROOT", repo)
    monkeypatch.setattr(audit, "VAULT_ROOT", vault)
    monkeypatch.setattr(audit, "CAPABILITY_DOMAINS", {"test": {"required_labels": ["[code: scripts/ops/ci_gate.py]"]}})

    result = audit.audit_required_authorities(
        {"required_authorities": {"test": [
            _authority_row("[code: scripts/ops/ci_gate.py]", "01_System/First.md"),
            _authority_row("[code: scripts/ops/ci_gate.py]", "01_System/Second.md"),
        ]}}
    )

    assert result["status"] == "FAIL"
    assert result["duplicate_labels"] == ["[code: scripts/ops/ci_gate.py]"]


def test_missing_authority_page_fails_closed(tmp_path: Path, monkeypatch):
    audit = importlib.import_module("scripts.ops.wiki_capability_coverage_audit")
    repo = tmp_path / "repo"
    vault = repo / "nexus_wiki_vault"
    (repo / "scripts" / "ops").mkdir(parents=True)
    (repo / "scripts" / "ops" / "ci_gate.py").write_text("def main():\n    return 0\n")
    vault.mkdir(parents=True)
    monkeypatch.setattr(audit, "REPO_ROOT", repo)
    monkeypatch.setattr(audit, "VAULT_ROOT", vault)
    monkeypatch.setattr(audit, "CAPABILITY_DOMAINS", {"test": {"required_labels": ["[code: scripts/ops/ci_gate.py]"]}})

    result = audit.audit_required_authorities(
        {"required_authorities": {"test": [
            _authority_row("[code: scripts/ops/ci_gate.py]", "01_System/Missing.md"),
        ]}}
    )

    assert result["status"] == "FAIL"
    assert "test[0]:missing_authority_page:01_System/Missing.md" in result["missing"]
