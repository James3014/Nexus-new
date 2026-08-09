from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.ops.openwiki_authority_crosswalk import (
    AUTHORITY,
    compile_crosswalk,
    load_mapping_rules,
    main,
    render_crosswalk,
    resolve_implementation_key,
)

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "nexus_wiki_vault/99_Schema/WIKI_AUTHORITY_MANIFEST.yaml"


def _record(report: dict, page: str, key: str) -> dict:
    return next(
        row
        for row in report["records"]
        if row["openwiki_page"] == page and row["implementation_key"] == key
    )


def _rule(
    rule_id: str,
    page: str,
    *,
    paths: list[str] | None = None,
    prefixes: list[str] | None = None,
) -> dict:
    return {
        "id": rule_id,
        "authority_page": page,
        "authority_classification": "active",
        "code_paths": paths or [],
        "code_path_prefixes": prefixes or [],
    }


def test_real_pilot_maps_core_services_and_ops_from_manifest():
    report = compile_crosswalk(ROOT / "openwiki", MANIFEST)

    core = _record(
        report,
        "quickstart.md",
        "nexus/engine/capability_planner.py",
    )
    services = _record(
        report,
        "architecture/overview.md",
        "nexus/services/unified_runtime.py",
    )
    ops = _record(
        report,
        "runtime/cli-and-cueline.md",
        "scripts/ops/nexus_cueline_worker.py",
    )

    assert core["mapping_status"] == "EXACT_PREFIX_MATCH"
    assert core["authority_page"] == "01_System/SYSTEM_ARCHITECTURE_BLUEPRINT.md"
    assert services["mapping_status"] == "EXACT_PREFIX_MATCH"
    assert services["authority_page"] == "02_Modules/Module - Runtime Services.md"
    assert ops["mapping_status"] == "EXACT_PREFIX_MATCH"
    assert ops["authority_page"] == "06_Ops/Ops - CI/CD Promotion Gate.md"


def test_real_uncovered_workflow_stays_unmapped_without_guessing():
    report = compile_crosswalk(ROOT / "openwiki", MANIFEST)
    record = _record(
        report,
        "workflows/github-actions.md",
        ".github/workflows/openwiki-update.yml",
    )

    assert record["mapping_status"] == "UNMAPPED"
    assert record["authority_page"] is None
    assert record["mapping_basis"] == {
        "kind": "NONE",
        "matched_values": [],
        "rule_ids": [],
    }


def test_exact_path_has_governed_precedence_over_prefix():
    rules = [
        _rule("prefix", "Prefix.md", prefixes=["scripts/ops/"]),
        _rule("exact", "Exact.md", paths=["scripts/ops/ci_gate.py"]),
    ]

    result = resolve_implementation_key("scripts/ops/ci_gate.py", rules)

    assert result["mapping_status"] == "EXACT_PATH_MATCH"
    assert result["authority_page"] == "Exact.md"
    assert result["mapping_basis"]["rule_ids"] == ["exact"]


def test_longest_prefix_has_governed_precedence():
    rules = [
        _rule("broad", "Broad.md", prefixes=["scripts/"]),
        _rule("narrow", "Narrow.md", prefixes=["scripts/ops/"]),
    ]

    result = resolve_implementation_key("scripts/ops/tool.py", rules)

    assert result["mapping_status"] == "EXACT_PREFIX_MATCH"
    assert result["authority_page"] == "Narrow.md"
    assert result["mapping_basis"]["rule_ids"] == ["narrow"]


def test_equal_precedence_conflict_fails_closed_as_ambiguous():
    rules = [
        _rule("a", "A.md", prefixes=["nexus/core/"]),
        _rule("b", "B.md", prefixes=["nexus/core/"]),
    ]

    result = resolve_implementation_key("nexus/core/state.py", rules)

    assert result["mapping_status"] == "AMBIGUOUS"
    assert result["authority_page"] is None
    assert result["mapping_basis"]["rule_ids"] == ["a", "b"]
    assert [row["authority_page"] for row in result["candidates"]] == ["A.md", "B.md"]


def test_equal_precedence_same_authority_is_not_false_ambiguity():
    rules = [
        _rule("a", "Same.md", prefixes=["nexus/core/"]),
        _rule("b", "Same.md", prefixes=["nexus/core/"]),
    ]

    result = resolve_implementation_key("nexus/core/state.py", rules)

    assert result["mapping_status"] == "EXACT_PREFIX_MATCH"
    assert result["authority_page"] == "Same.md"
    assert result["mapping_basis"]["rule_ids"] == ["a", "b"]


def test_symbols_are_preserved_but_never_cross_product_mapped():
    report = compile_crosswalk(ROOT / "openwiki", MANIFEST)
    record = _record(
        report,
        "quickstart.md",
        "scripts/engine/nexus_cli.py",
    )

    assert record["declared_symbols"] == ["CapabilityPlanner", "nexus"]
    assert record["symbol_mapping_status"] == "UNPAIRED_METADATA_NOT_USED_FOR_AUTHORITY"
    assert "symbol" not in record["mapping_basis"]


def test_crosswalk_is_byte_deterministic_and_non_authoritative():
    first = compile_crosswalk(ROOT / "openwiki", MANIFEST)
    second = compile_crosswalk(ROOT / "openwiki", MANIFEST)

    assert render_crosswalk(first) == render_crosswalk(second)
    assert first["authority"] == AUTHORITY
    assert first["record_count"] == len(first["records"])
    assert sum(first["status_counts"].values()) == first["record_count"]
    assert "alone declares governed-Wiki authority" in first["authority_ceiling"]


def test_cli_writes_and_checks_same_artifact(tmp_path: Path):
    output = tmp_path / "crosswalk.json"
    argv = [
        "--openwiki-root",
        str(ROOT / "openwiki"),
        "--authority-manifest",
        str(MANIFEST),
        "--output",
        str(output),
    ]

    assert main(argv) == 0
    assert main([*argv, "--check"]) == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["schema"] == "nexus.openwiki_wiki_crosswalk.v1"

    output.write_text("{}\n", encoding="utf-8")
    assert main([*argv, "--check"]) == 1


def test_invalid_or_escaping_paths_fail_closed():
    rules = load_mapping_rules({
        "code_symbol_mapping_rules": [_rule("safe", "Safe.md", prefixes=["nexus/"])]
    })

    with pytest.raises(ValueError, match="invalid repository-relative path"):
        resolve_implementation_key("../secret", rules)


def test_malformed_or_duplicate_manifest_rules_fail_closed():
    malformed = _rule("bad", "Bad.md")
    malformed["code_paths"] = "nexus/core/state.py"
    with pytest.raises(ValueError, match="code_paths must be a string list"):
        load_mapping_rules({"code_symbol_mapping_rules": [malformed]})

    duplicate = _rule("same", "Same.md", prefixes=["nexus/"])
    with pytest.raises(ValueError, match="duplicate mapping rule id"):
        load_mapping_rules({"code_symbol_mapping_rules": [duplicate, duplicate]})


def test_missing_input_roots_fail_closed(tmp_path: Path):
    with pytest.raises(ValueError, match="OpenWiki root is not a directory"):
        compile_crosswalk(tmp_path / "missing-openwiki", MANIFEST)

    openwiki_root = tmp_path / "openwiki"
    openwiki_root.mkdir()
    with pytest.raises(ValueError, match="authority manifest is not a file"):
        compile_crosswalk(openwiki_root, tmp_path / "missing-manifest.yaml")


def test_manifest_schema_and_duplicate_keys_fail_closed(tmp_path: Path):
    wrong_schema = tmp_path / "wrong-schema.yaml"
    wrong_schema.write_text(
        "schema: wrong.schema\ncode_symbol_mapping_rules: []\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="manifest schema must equal"):
        compile_crosswalk(ROOT / "openwiki", wrong_schema)

    duplicate = tmp_path / "duplicate.yaml"
    duplicate.write_text(
        "schema: nexus.wiki.authority.v1\n"
        "schema: substituted.schema\n"
        "code_symbol_mapping_rules: []\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate key 'schema'"):
        compile_crosswalk(ROOT / "openwiki", duplicate)


def test_non_string_authority_identity_fields_fail_closed():
    invalid = _rule("bad", "Bad.md", prefixes=["nexus/"])
    invalid["authority_page"] = 7

    with pytest.raises(ValueError, match="identity/authority fields must be strings"):
        load_mapping_rules({"code_symbol_mapping_rules": [invalid]})
