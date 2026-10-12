from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

import pytest
import yaml

from scripts.ops import check_operating_mode as com

ROOT = Path(__file__).resolve().parents[2]
REAL_MODE_FILE = ROOT / "docs/governance/current_operating_mode.yaml"
SCRIPT = ROOT / "scripts/ops/check_operating_mode.py"


def _real_text() -> str:
    return REAL_MODE_FILE.read_text(encoding="utf-8")


def _write(tmp_path: Path, text: str | bytes) -> Path:
    path = tmp_path / "current_operating_mode.yaml"
    if isinstance(text, bytes):
        path.write_bytes(text)
    else:
        path.write_text(text, encoding="utf-8")
    return path


def _mutated(tmp_path: Path, mutate: Callable[[dict[str, Any]], None]) -> Path:
    doc = yaml.safe_load(_real_text())
    mutate(doc)
    return _write(tmp_path, yaml.safe_dump(doc, sort_keys=False))


def _replace_once(old: str, new: str) -> str:
    text = _real_text()
    assert text.count(old) == 1, old
    return text.replace(old, new)


def _assert_decision_required(result: dict[str, Any], code: str) -> None:
    assert result["schema"] == com.SCHEMA
    assert result["status"] == com.STATUS_DECISION_REQUIRED
    assert result["default_execution"] is None
    assert result["reasons"]
    codes = {reason["code"] for reason in result["reasons"]}
    assert code in codes, result["reasons"]
    assert codes <= set(com.REASON_CODES)


# --- the checked-in file -------------------------------------------------------


def test_checked_in_operating_mode_file_is_valid() -> None:
    result = com.evaluate_operating_mode(REAL_MODE_FILE)
    assert result["status"] == com.STATUS_VALID
    assert result["reasons"] == []
    assert result["schema"] == "nexus.operating_mode_check.v1"
    doc = yaml.safe_load(_real_text())
    assert result["default_execution"] == {
        "primary_bounded_work": doc["default_execution"]["primary_bounded_work"],
        "delegated_bounded_work": doc["default_execution"]["delegated_bounded_work"],
    }
    assert len(result["source_sha256"]) == 64


def test_evaluated_keys_still_exist_in_real_file() -> None:
    doc = yaml.safe_load(_real_text())
    for dotted in com.EVALUATED_KEY_PATHS:
        node: Any = doc
        for part in dotted.split("."):
            assert isinstance(node, dict) and part in node, f"drift: {dotted} missing"
            node = node[part]
    assert set(doc) == set(com.KNOWN_TOP_LEVEL_KEYS)
    assert doc["mode"] in com.KNOWN_MODES
    assert set(doc["protected_merge"]) == set(com.LANES)


# --- file-level fail-closed cases ----------------------------------------------


def test_missing_file_requires_owner_lane_decision(tmp_path: Path) -> None:
    result = com.evaluate_operating_mode(tmp_path / "absent.yaml")
    _assert_decision_required(result, com.MODE_FILE_MISSING)
    assert result["source_sha256"] is None


def test_unreadable_path_requires_owner_lane_decision(tmp_path: Path) -> None:
    directory = tmp_path / "current_operating_mode.yaml"
    directory.mkdir()
    _assert_decision_required(com.evaluate_operating_mode(directory), com.MODE_FILE_UNREADABLE)


@pytest.mark.skipif(
    not hasattr(os, "geteuid") or os.geteuid() == 0, reason="root ignores file permissions"
)
def test_permission_denied_requires_owner_lane_decision(tmp_path: Path) -> None:
    path = _write(tmp_path, _real_text())
    path.chmod(0)
    try:
        _assert_decision_required(com.evaluate_operating_mode(path), com.MODE_FILE_UNREADABLE)
    finally:
        path.chmod(0o600)


def test_non_utf8_file_requires_owner_lane_decision(tmp_path: Path) -> None:
    path = _write(tmp_path, _real_text().encode("utf-8") + b"\n# \xff\xfe\n")
    _assert_decision_required(com.evaluate_operating_mode(path), com.MODE_FILE_NOT_UTF8)


def test_yaml_parse_error_requires_owner_lane_decision(tmp_path: Path) -> None:
    path = _write(tmp_path, _real_text() + "\nbroken: [unterminated\n")
    _assert_decision_required(com.evaluate_operating_mode(path), com.YAML_PARSE_ERROR)


def test_multiple_yaml_documents_require_owner_lane_decision(tmp_path: Path) -> None:
    path = _write(tmp_path, _real_text() + "\n---\nmode: BOOTSTRAP\n")
    _assert_decision_required(com.evaluate_operating_mode(path), com.YAML_PARSE_ERROR)


def test_duplicate_top_level_key_is_ambiguous(tmp_path: Path) -> None:
    path = _write(tmp_path, _real_text() + "\nmode: BOOTSTRAP\n")
    _assert_decision_required(com.evaluate_operating_mode(path), com.DUPLICATE_KEY)


def test_duplicate_nested_lane_key_is_ambiguous(tmp_path: Path) -> None:
    text = _replace_once(
        "  delegated_bounded_work: DIRECT_DELEGATED\n",
        "  delegated_bounded_work: DIRECT_DELEGATED\n  primary_bounded_work: GOVERNED\n",
    )
    _assert_decision_required(
        com.evaluate_operating_mode(_write(tmp_path, text)), com.DUPLICATE_KEY
    )


def test_yaml_merge_key_is_ambiguous(tmp_path: Path) -> None:
    text = _replace_once(
        "default_execution:\n",
        "default_execution:\n  <<: {primary_bounded_work: GOVERNED}\n",
    )
    _assert_decision_required(
        com.evaluate_operating_mode(_write(tmp_path, text)), com.DUPLICATE_KEY
    )


@pytest.mark.parametrize("text", ["", "- mode: BOOTSTRAP\n", "BOOTSTRAP\n"])
def test_top_level_not_mapping_requires_owner_lane_decision(tmp_path: Path, text: str) -> None:
    _assert_decision_required(
        com.evaluate_operating_mode(_write(tmp_path, text)), com.TOP_LEVEL_NOT_MAPPING
    )


# --- contract-level fail-closed cases -------------------------------------------


def test_unknown_top_level_key_is_ambiguous(tmp_path: Path) -> None:
    path = _write(tmp_path, _real_text() + "\ndefault_lane_override: GOVERNED\n")
    _assert_decision_required(com.evaluate_operating_mode(path), com.UNKNOWN_TOP_LEVEL_KEY)


def test_schema_mismatch_requires_owner_lane_decision(tmp_path: Path) -> None:
    text = _replace_once("schema: nexus.operating_mode.v1\n", "schema: nexus.operating_mode.v2\n")
    _assert_decision_required(
        com.evaluate_operating_mode(_write(tmp_path, text)), com.SCHEMA_MISMATCH
    )


@pytest.mark.parametrize(
    "mode", ["GOVERNED_DEFAULT", "NEXUS_GOVERNANCE_DEFAULT_READY", "bootstrap"]
)
def test_unknown_mode_requires_owner_lane_decision(tmp_path: Path, mode: str) -> None:
    text = _replace_once("mode: BOOTSTRAP\n", f"mode: {mode}\n")
    _assert_decision_required(com.evaluate_operating_mode(_write(tmp_path, text)), com.UNKNOWN_MODE)


def test_missing_mode_requires_owner_lane_decision(tmp_path: Path) -> None:
    path = _mutated(tmp_path, lambda doc: doc.pop("mode"))
    _assert_decision_required(com.evaluate_operating_mode(path), com.UNKNOWN_MODE)


@pytest.mark.parametrize("key", ["primary_bounded_work", "delegated_bounded_work"])
def test_invalid_default_lane_requires_owner_lane_decision(tmp_path: Path, key: str) -> None:
    path = _mutated(tmp_path, lambda doc: doc["default_execution"].__setitem__(key, "OWNER_DIRECT"))
    _assert_decision_required(com.evaluate_operating_mode(path), com.DEFAULT_LANE_INVALID)


@pytest.mark.parametrize("key", ["primary_bounded_work", "delegated_bounded_work"])
def test_missing_default_lane_requires_owner_lane_decision(tmp_path: Path, key: str) -> None:
    path = _mutated(tmp_path, lambda doc: doc["default_execution"].pop(key))
    _assert_decision_required(com.evaluate_operating_mode(path), com.DEFAULT_LANE_MISSING)


def test_missing_default_execution_requires_owner_lane_decision(tmp_path: Path) -> None:
    path = _mutated(tmp_path, lambda doc: doc.pop("default_execution"))
    _assert_decision_required(com.evaluate_operating_mode(path), com.DEFAULT_EXECUTION_INVALID)


def test_unknown_default_execution_key_is_ambiguous(tmp_path: Path) -> None:
    path = _mutated(
        tmp_path, lambda doc: doc["default_execution"].__setitem__("other_work", "GOVERNED")
    )
    _assert_decision_required(com.evaluate_operating_mode(path), com.DEFAULT_EXECUTION_UNKNOWN_KEY)


@pytest.mark.parametrize("lane", ["DIRECT_CANONICAL", "DIRECT_DELEGATED", "GOVERNED"])
def test_protected_merge_missing_lane_requires_owner_lane_decision(
    tmp_path: Path, lane: str
) -> None:
    path = _mutated(tmp_path, lambda doc: doc["protected_merge"].pop(lane))
    _assert_decision_required(com.evaluate_operating_mode(path), com.PROTECTED_MERGE_LANE_MISSING)


def test_protected_merge_not_mapping_requires_owner_lane_decision(tmp_path: Path) -> None:
    path = _mutated(tmp_path, lambda doc: doc.__setitem__("protected_merge", ["GOVERNED"]))
    _assert_decision_required(com.evaluate_operating_mode(path), com.PROTECTED_MERGE_INVALID)


def test_protected_merge_unknown_lane_is_ambiguous(tmp_path: Path) -> None:
    path = _mutated(
        tmp_path, lambda doc: doc["protected_merge"].__setitem__("OWNER_DIRECT", {"x": 1})
    )
    _assert_decision_required(com.evaluate_operating_mode(path), com.PROTECTED_MERGE_UNKNOWN_LANE)


@pytest.mark.parametrize("value", ["USE_DEFAULT_LANE", None])
def test_fail_closed_rule_must_require_owner_lane(tmp_path: Path, value: str | None) -> None:
    def mutate(doc: dict[str, Any]) -> None:
        if value is None:
            doc["fail_closed"].pop("missing_invalid_or_ambiguous_mode")
        else:
            doc["fail_closed"]["missing_invalid_or_ambiguous_mode"] = value

    path = _mutated(tmp_path, mutate)
    _assert_decision_required(com.evaluate_operating_mode(path), com.FAIL_CLOSED_RULE_INVALID)


@pytest.mark.parametrize("value", ["ALLOWED", None])
def test_silent_downgrade_must_be_forbidden(tmp_path: Path, value: str | None) -> None:
    def mutate(doc: dict[str, Any]) -> None:
        if value is None:
            doc["transition"].pop("silent_governed_to_direct_downgrade")
        else:
            doc["transition"]["silent_governed_to_direct_downgrade"] = value

    path = _mutated(tmp_path, mutate)
    _assert_decision_required(com.evaluate_operating_mode(path), com.SILENT_DOWNGRADE_NOT_FORBIDDEN)


@pytest.mark.parametrize("value", ["true", "0", "'false'", "null"])
def test_auto_chain_must_be_boolean_false(tmp_path: Path, value: str) -> None:
    text = _replace_once("auto_chain: false\n", f"auto_chain: {value}\n")
    _assert_decision_required(
        com.evaluate_operating_mode(_write(tmp_path, text)), com.AUTO_CHAIN_NOT_FALSE
    )


def test_missing_auto_chain_requires_owner_lane_decision(tmp_path: Path) -> None:
    path = _mutated(tmp_path, lambda doc: doc.pop("auto_chain"))
    _assert_decision_required(com.evaluate_operating_mode(path), com.AUTO_CHAIN_NOT_FALSE)


@pytest.mark.parametrize("value", [[], "security_boundary_weakening", ["ok", 3], ["ok", ""], None])
def test_escalation_list_must_be_non_empty_strings(tmp_path: Path, value: Any) -> None:
    def mutate(doc: dict[str, Any]) -> None:
        if value is None:
            doc.pop("escalate_to_governed_when")
        else:
            doc["escalate_to_governed_when"] = value

    path = _mutated(tmp_path, mutate)
    _assert_decision_required(com.evaluate_operating_mode(path), com.ESCALATION_LIST_INVALID)


# --- global invariants -----------------------------------------------------------


def test_multiple_violations_are_all_reported_without_lane_selection(tmp_path: Path) -> None:
    def mutate(doc: dict[str, Any]) -> None:
        doc["mode"] = "UNKNOWN"
        doc["auto_chain"] = True
        doc["transition"]["silent_governed_to_direct_downgrade"] = "ALLOWED"

    result = com.evaluate_operating_mode(_mutated(tmp_path, mutate))
    codes = {reason["code"] for reason in result["reasons"]}
    assert {com.UNKNOWN_MODE, com.AUTO_CHAIN_NOT_FALSE, com.SILENT_DOWNGRADE_NOT_FORBIDDEN} <= codes
    assert result["status"] == com.STATUS_DECISION_REQUIRED
    assert result["default_execution"] is None


def test_round_tripped_real_file_stays_valid(tmp_path: Path) -> None:
    path = _mutated(tmp_path, lambda doc: None)
    assert com.evaluate_operating_mode(path)["status"] == com.STATUS_VALID


# --- CLI ---------------------------------------------------------------------------


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
    )


def test_cli_exits_zero_for_checked_in_file() -> None:
    proc = _run_cli()
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["status"] == com.STATUS_VALID
    assert (
        payload["default_execution"]
        == com.evaluate_operating_mode(REAL_MODE_FILE)["default_execution"]
    )


def test_cli_exits_two_when_owner_lane_decision_required(tmp_path: Path) -> None:
    proc = _run_cli("--path", str(tmp_path / "absent.yaml"))
    assert proc.returncode == 2, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["status"] == com.STATUS_DECISION_REQUIRED
    assert payload["default_execution"] is None
    assert payload["reasons"][0]["code"] == com.MODE_FILE_MISSING


def test_cli_exits_two_for_duplicate_key(tmp_path: Path) -> None:
    path = _write(tmp_path, _real_text() + "\nauto_chain: false\n")
    proc = _run_cli("--path", str(path))
    assert proc.returncode == 2, proc.stderr
    assert json.loads(proc.stdout)["reasons"][0]["code"] == com.DUPLICATE_KEY
