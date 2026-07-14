from pathlib import Path

from scripts.ops import wiki_coverage_audit as audit


def _repo_with_source(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    source = repo / "src" / "runtime.py"
    source.parent.mkdir(parents=True)
    source.write_text("class Runtime:\n    def run(self):\n        return True\n")
    vault = repo / "nexus_wiki_vault"
    vault.mkdir()
    return repo, vault


def _mapping() -> dict:
    return {
        "code_path": "src/runtime.py",
        "symbol": "Runtime.run",
        "authority_page": "03_Flows/Runtime.md",
        "authority_classification": "current",
        "source_evidence": {
            "source_path": "src/runtime.py",
            "kind": "code",
            "ref": "Runtime.run",
        },
    }


def test_policy_declares_taxonomy_and_exact_matching():
    policy = audit.coverage_policy()

    assert set(policy["taxonomy"]) == set(audit.COVERAGE_TAXONOMY)
    assert policy["threshold"] == 0.85
    assert policy["matching"] == "exact_code_path_and_symbol_only"
    assert policy["fuzzy_basename_matches_are_not_coverage"] is True


def test_code_item_taxonomy_covers_required_classes():
    assert audit.classify_coverage_item("scripts/ops/ci_gate.py") == "must_document"
    assert audit.classify_coverage_item("nexus/core/router.py") == "should_document"
    assert audit.classify_coverage_item("tests/test_router.py") == "test_only"
    assert audit.classify_coverage_item("build/generated/router.py") == "generated"
    assert audit.classify_coverage_item("90_Sources/Legacy_Wiki/old.py") == "legacy"
    assert audit.classify_coverage_item("nexus/core/deprecated/router.py") == "deprecated"
    assert audit.classify_coverage_item("nexus/core/router.py", "_helper") == "internal_helper"
    assert audit.classify_coverage_item(
        "nexus/core/router.py", allowed_exclusion=True
    ) == "allowed_exclusion"


def test_symbol_inventory_is_ast_based_and_classified(tmp_path: Path, monkeypatch):
    repo = tmp_path / "repo"
    runtime = repo / "src" / "runtime.py"
    runtime.parent.mkdir(parents=True)
    runtime.write_text(
        "class Runtime:\n"
        "    def run(self):\n"
        "        return True\n"
        "    def _private(self):\n"
        "        return False\n"
    )
    test_file = repo / "tests" / "test_runtime.py"
    test_file.parent.mkdir()
    test_file.write_text("def test_runtime():\n    assert True\n")

    monkeypatch.setattr(audit, "REPO_ROOT", repo)
    monkeypatch.setattr(audit, "SYMBOL_SCAN_DIRS", ["src", "tests"])

    inventory = audit.get_symbol_inventory()
    classifications = {(item["code_path"], item["symbol"]): item["classification"] for item in inventory}

    assert classifications[("src/runtime.py", "__module__")] == "should_document"
    assert classifications[("src/runtime.py", "Runtime")] == "should_document"
    assert classifications[("src/runtime.py", "Runtime.run")] == "should_document"
    assert classifications[("src/runtime.py", "Runtime._private")] == "internal_helper"
    assert classifications[("tests/test_runtime.py", "test_runtime")] == "test_only"


def test_valid_mapping_requires_exact_code_and_current_authority(
    tmp_path: Path,
):
    repo, vault = _repo_with_source(tmp_path)

    assert audit.validate_mapping(
        _mapping(),
        repo,
        vault,
        authority_pages={"03_Flows/Runtime.md": {"classification": "current"}},
    ) == []


def test_mapping_rejects_missing_code_path(tmp_path: Path):
    repo, vault = _repo_with_source(tmp_path)
    mapping = _mapping()
    mapping["code_path"] = "src/missing.py"
    mapping["source_evidence"]["source_path"] = "src/missing.py"

    errors = audit.validate_mapping(
        mapping,
        repo,
        vault,
        authority_pages={"03_Flows/Runtime.md": {"classification": "current"}},
    )

    assert "missing_code_path" in errors


def test_mapping_rejects_filename_only_symbol(tmp_path: Path):
    repo, vault = _repo_with_source(tmp_path)
    mapping = _mapping()
    mapping["symbol"] = "runtime.py"

    errors = audit.validate_mapping(
        mapping,
        repo,
        vault,
        authority_pages={"03_Flows/Runtime.md": {"classification": "current"}},
    )

    assert "symbol_is_filename_only" in errors


def test_mapping_rejects_nonexistent_python_symbol(tmp_path: Path):
    repo, vault = _repo_with_source(tmp_path)
    mapping = _mapping()
    mapping["symbol"] = "Runtime.missing"

    errors = audit.validate_mapping(
        mapping,
        repo,
        vault,
        authority_pages={"03_Flows/Runtime.md": {"classification": "current"}},
    )

    assert "missing_symbol" in errors


def test_mapping_rejects_missing_exact_authority_page(tmp_path: Path):
    repo, vault = _repo_with_source(tmp_path)
    mapping = _mapping()
    mapping["authority_page"] = "Runtime"

    errors = audit.validate_mapping(
        mapping,
        repo,
        vault,
        authority_pages={"03_Flows/Runtime.md": {"classification": "current"}},
    )

    assert "missing_authority_page" in errors


def test_mapping_rejects_legacy_authority(tmp_path: Path):
    repo, vault = _repo_with_source(tmp_path)
    mapping = _mapping()
    mapping["authority_page"] = "90_Sources/Legacy_Wiki/Runtime.md"

    errors = audit.validate_mapping(mapping, repo, vault)

    assert "invalid_authority_classification:legacy" in errors


def test_mapping_rejects_generated_authority(tmp_path: Path):
    repo, vault = _repo_with_source(tmp_path)
    mapping = _mapping()
    mapping["authority_page"] = "99_Schema/generated/Runtime.md"

    errors = audit.validate_mapping(mapping, repo, vault)

    assert "invalid_authority_classification:generated" in errors


def test_mapping_rejects_source_evidence_path_mismatch(tmp_path: Path):
    repo, vault = _repo_with_source(tmp_path)
    mapping = _mapping()
    mapping["source_evidence"]["source_path"] = "src/other.py"

    errors = audit.validate_mapping(
        mapping,
        repo,
        vault,
        authority_pages={"03_Flows/Runtime.md": {"classification": "current"}},
    )

    assert "source_evidence_path_mismatch" in errors


def test_mapping_rejects_duplicate_code_symbol_mapping(tmp_path: Path):
    repo, vault = _repo_with_source(tmp_path)
    result = audit.validate_mappings(
        [_mapping(), _mapping()],
        repo,
        vault,
        authority_pages={"03_Flows/Runtime.md": {"classification": "current"}},
    )

    assert result["valid_count"] == 1
    assert result["error_count"] == 1
    assert result["errors"][0]["errors"] == ["duplicate_code_symbol_mapping"]
