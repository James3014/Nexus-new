from copy import deepcopy
from pathlib import Path

import pytest

from scripts.ops import wiki_coverage_audit as audit
from scripts.ops.openwiki_authority_crosswalk import compile_crosswalk


def test_crosswalk_alignment_regenerates_current_inputs() -> None:
    result = audit.build_crosswalk_alignment()

    assert result["schema"] == "nexus.openwiki_wiki_crosswalk.v1"
    assert result["authority"] == "derived_non_authoritative"
    assert result["record_count"] == 24
    assert result["status_counts"] == {
        "EXACT_PREFIX_MATCH": 10,
        "UNMAPPED": 14,
    }
    assert result["alignment_status"] == "PASS"
    assert result["mapped_count"] == 10
    assert result["unmapped_count"] == 14
    assert result["ambiguous_count"] == 0


def test_formal_mapping_report_exposes_crosswalk_alignment() -> None:
    result = audit.formal_mapping_report(
        audit.get_symbol_inventory(), audit.load_authority_manifest()
    )

    assert result["crosswalk_alignment"]["alignment_status"] == "PASS"
    assert result["crosswalk_alignment"]["status_counts"]["UNMAPPED"] == 14


def test_crosswalk_alignment_keeps_unmapped_out_of_scope() -> None:
    result = audit.build_crosswalk_alignment(formal_scope={"nexus/services/unified_runtime.py"})

    assert result["alignment_status"] == "PASS"
    assert result["unmapped_count"] == 14
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
    tampered["status_counts"] = {"AMBIGUOUS": 1, "EXACT_PREFIX_MATCH": 9, "UNMAPPED": 14}
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
