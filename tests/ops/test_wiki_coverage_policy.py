from copy import deepcopy
from pathlib import Path

import pytest

from scripts.ops import wiki_coverage_audit as audit
from scripts.ops.openwiki_authority_crosswalk import compile_crosswalk


def test_crosswalk_alignment_regenerates_current_inputs() -> None:
    result = audit.build_crosswalk_alignment()

    assert result["schema"] == "nexus.openwiki_wiki_crosswalk.v1"
    assert result["authority"] == "derived_non_authoritative"
    assert result["record_count"] == 22
    assert result["status_counts"] == {
        "EXACT_PREFIX_MATCH": 10,
        "UNMAPPED": 12,
    }
    assert result["alignment_status"] == "PASS"
    assert result["mapped_count"] == 10
    assert result["unmapped_count"] == 12
    assert result["ambiguous_count"] == 0


def test_formal_mapping_report_exposes_crosswalk_alignment() -> None:
    result = audit.formal_mapping_report(
        audit.get_symbol_inventory(), audit.load_authority_manifest()
    )

    assert result["crosswalk_alignment"]["alignment_status"] == "PASS"
    assert result["crosswalk_alignment"]["status_counts"]["UNMAPPED"] == 12


def test_crosswalk_alignment_keeps_unmapped_out_of_scope() -> None:
    result = audit.build_crosswalk_alignment(formal_scope={"nexus/services/unified_runtime.py"})

    assert result["alignment_status"] == "PASS"
    assert result["unmapped_count"] == 12
    assert result["scoped_unmapped_count"] == 0
    assert all(record["authority_page"] is None for record in result["unmapped_records"])


def test_crosswalk_alignment_fails_for_scoped_unmapped() -> None:
    result = audit.build_crosswalk_alignment(formal_scope={".github/workflows/openwiki-update.yml"})

    assert result["alignment_status"] == "FAIL"
    assert result["scoped_unmapped_count"] == 1


def test_crosswalk_contract_rejects_schema_identity_and_count_tampering() -> None:
    root = Path(__file__).resolve().parents[2]
    source = compile_crosswalk(
        root / "openwiki",
        root / "nexus_wiki_vault/99_Schema/WIKI_AUTHORITY_MANIFEST.yaml",
    )

    for field, value in (
        ("schema", "wrong.schema"),
        ("input_sha256", "tampered"),
        ("record_count", source["record_count"] + 1),
        ("status_counts", {"EXACT_PREFIX_MATCH": 9, "UNMAPPED": 12}),
    ):
        tampered = deepcopy(source)
        tampered[field] = value
        with pytest.raises(ValueError):
            audit.validate_crosswalk_report(tampered)


def test_crosswalk_contract_rejects_valid_hex_identity_tamper() -> None:
    root = Path(__file__).resolve().parents[2]
    canonical = compile_crosswalk(
        root / "openwiki",
        root / "nexus_wiki_vault/99_Schema/WIKI_AUTHORITY_MANIFEST.yaml",
    )
    tampered = deepcopy(canonical)
    tampered["input_sha256"] = "0" * 64

    with pytest.raises(ValueError, match="current canonical inputs"):
        audit.validate_crosswalk_report(tampered)


def test_crosswalk_contract_rejects_caller_supplied_canonical_bypass() -> None:
    root = Path(__file__).resolve().parents[2]
    tampered = compile_crosswalk(
        root / "openwiki",
        root / "nexus_wiki_vault/99_Schema/WIKI_AUTHORITY_MANIFEST.yaml",
    )
    tampered["input_sha256"] = "0" * 64

    with pytest.raises(TypeError, match="canonical_report"):
        audit.validate_crosswalk_report(tampered, canonical_report=tampered)


@pytest.mark.parametrize(
    ("field", "replacement"),
    (
        ("authority_page", "01_System/OTHER_AUTHORITY.md"),
        ("authority_classification", "current"),
    ),
)
def test_crosswalk_contract_rejects_mapped_authority_mismatch(
    field: str,
    replacement: str,
) -> None:
    root = Path(__file__).resolve().parents[2]
    canonical = compile_crosswalk(
        root / "openwiki",
        root / "nexus_wiki_vault/99_Schema/WIKI_AUTHORITY_MANIFEST.yaml",
    )
    tampered = deepcopy(canonical)
    mapped = next(
        record
        for record in tampered["records"]
        if record["mapping_status"] in {"EXACT_PATH_MATCH", "EXACT_PREFIX_MATCH"}
    )
    mapped[field] = replacement

    with pytest.raises(ValueError, match="current canonical inputs"):
        audit.validate_crosswalk_report(tampered)


def test_crosswalk_contract_rejects_duplicate_record_identity() -> None:
    root = Path(__file__).resolve().parents[2]
    canonical = compile_crosswalk(
        root / "openwiki",
        root / "nexus_wiki_vault/99_Schema/WIKI_AUTHORITY_MANIFEST.yaml",
    )
    tampered = deepcopy(canonical)
    duplicate = deepcopy(tampered["records"][0])
    tampered["records"].append(duplicate)
    tampered["record_count"] += 1
    status = duplicate["mapping_status"]
    tampered["status_counts"][status] += 1

    with pytest.raises(ValueError, match="duplicate crosswalk record identity"):
        audit.validate_crosswalk_report(tampered)


def test_crosswalk_contract_rejects_empty_implementation_key() -> None:
    root = Path(__file__).resolve().parents[2]
    canonical = compile_crosswalk(
        root / "openwiki",
        root / "nexus_wiki_vault/99_Schema/WIKI_AUTHORITY_MANIFEST.yaml",
    )
    tampered = deepcopy(canonical)
    tampered["records"][0]["implementation_key"] = ""

    with pytest.raises(ValueError, match="implementation key is invalid"):
        audit.validate_crosswalk_report(tampered)


def test_crosswalk_contract_rejects_unknown_mapping_status() -> None:
    root = Path(__file__).resolve().parents[2]
    canonical = compile_crosswalk(
        root / "openwiki",
        root / "nexus_wiki_vault/99_Schema/WIKI_AUTHORITY_MANIFEST.yaml",
    )
    tampered = deepcopy(canonical)
    tampered["records"][0]["mapping_status"] = "SYNTHETIC_MATCH"

    with pytest.raises(ValueError, match="unsupported crosswalk mapping status"):
        audit.validate_crosswalk_report(tampered)


def test_crosswalk_alignment_preserves_compiler_exception(monkeypatch) -> None:
    def fail_compile(*_args):
        raise ValueError("compiler input rejected")

    monkeypatch.setattr(audit, "compile_crosswalk", fail_compile)

    with pytest.raises(ValueError, match="compiler input rejected"):
        audit.build_crosswalk_alignment()


def test_crosswalk_alignment_fails_closed_for_scoped_ambiguous(monkeypatch) -> None:
    root = Path(__file__).resolve().parents[2]
    source = compile_crosswalk(
        root / "openwiki",
        root / "nexus_wiki_vault/99_Schema/WIKI_AUTHORITY_MANIFEST.yaml",
    )
    tampered = deepcopy(source)
    record = tampered["records"][0]
    record["mapping_status"] = "AMBIGUOUS"
    record["authority_page"] = None
    record["authority_classification"] = None
    tampered["status_counts"] = {"AMBIGUOUS": 1, "EXACT_PREFIX_MATCH": 9, "UNMAPPED": 12}
    monkeypatch.setattr(audit, "compile_crosswalk", lambda *_args: tampered)

    result = audit.build_crosswalk_alignment(formal_scope={record["implementation_key"]})

    assert result["alignment_status"] == "FAIL"
    assert result["ambiguous_count"] == 1
    assert result["scoped_ambiguous_count"] == 1
    assert result["ambiguous_records"][0]["authority_page"] is None


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
    assert (
        audit.classify_coverage_item("nexus/core/router.py", allowed_exclusion=True)
        == "allowed_exclusion"
    )


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
    classifications = {
        (item["code_path"], item["symbol"]): item["classification"] for item in inventory
    }

    assert classifications[("src/runtime.py", "__module__")] == "should_document"
    assert classifications[("src/runtime.py", "Runtime")] == "should_document"
    assert classifications[("src/runtime.py", "Runtime.run")] == "should_document"
    assert classifications[("src/runtime.py", "Runtime._private")] == "internal_helper"
    assert classifications[("tests/test_runtime.py", "test_runtime")] == "test_only"


def test_valid_mapping_requires_exact_code_and_current_authority(
    tmp_path: Path,
):
    repo, vault = _repo_with_source(tmp_path)

    assert (
        audit.validate_mapping(
            _mapping(),
            repo,
            vault,
            authority_pages={"03_Flows/Runtime.md": {"classification": "current"}},
        )
        == []
    )


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
