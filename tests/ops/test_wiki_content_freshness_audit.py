from pathlib import Path

from scripts.ops import wiki_content_freshness_audit as audit


def _fixture(tmp_path: Path) -> tuple[Path, Path, dict]:
    repo = tmp_path / "repo"
    source = repo / "scripts" / "ops" / "source.py"
    source.parent.mkdir(parents=True)
    source.write_text("def main():\n    return True\n", encoding="utf-8")
    vault = repo / "nexus_wiki_vault"
    schema = vault / "99_Schema"
    schema.mkdir(parents=True)
    page = vault / "01_System" / "Authority.md"
    page.parent.mkdir(parents=True)
    page.write_text(
        "---\nstatus: active\nowner: test-owner\nsource_of_truth: scripts/ops/source.py\n---\n# Authority\n",
        encoding="utf-8",
    )
    manifest = {
        "canonical": {"authority": {"path": "01_System/Authority.md", "authority": "normative"}},
        "known_legacy_entries": [],
        "content_freshness": {
            "page_overrides": {
                "01_System/Authority.md": {
                    "classification": "current_verified",
                    "source_paths": ["scripts/ops/source.py"],
                }
            },
            "symbol_contracts": {"scripts/ops/source.py": ["main"]},
            "verification_commands": [],
            "verification_tests": [],
        },
    }
    return repo, vault, manifest


def test_freshness_audit_requires_live_source_and_symbol(tmp_path: Path):
    repo, vault, manifest = _fixture(tmp_path)

    report = audit.build_report(repo, vault, manifest, run_commands=False)

    assert report["status"] == "PASS"
    assert report["summary"]["missing_source_path_count"] == 0
    assert report["symbols"][0]["symbols"] == [{"name": "main", "exists": True}]


def test_missing_source_path_fails_closed(tmp_path: Path):
    repo, vault, manifest = _fixture(tmp_path)
    manifest["content_freshness"]["page_overrides"]["01_System/Authority.md"][
        "source_paths"
    ] = ["scripts/ops/missing.py"]

    report = audit.build_report(repo, vault, manifest, run_commands=False)

    assert report["status"] == "FAIL"
    assert report["summary"]["missing_source_path_count"] == 1
    assert any(
        page["errors"] for page in report["pages"] if page["path"] == "01_System/Authority.md"
    )


def test_superseded_page_requires_current_successor(tmp_path: Path):
    repo, vault, manifest = _fixture(tmp_path)
    old = vault / "01_System" / "Old.md"
    old.write_text("---\nlifecycle: superseded\n---\n", encoding="utf-8")
    manifest["known_legacy_entries"] = [
        {"path": "01_System/Old.md", "classification": "superseded"}
    ]

    report = audit.build_report(repo, vault, manifest, run_commands=False)

    assert report["status"] == "FAIL"
    assert any(
        "missing_superseded_successor" in error
        for error in audit._lifecycle_checks(repo, vault, manifest)[1]
    )
