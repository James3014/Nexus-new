#!/usr/bin/env python3
"""Fail-closed validator for ``docs/governance/current_operating_mode.yaml``.

Authority: ``AGENTS.md`` (Authority bootstrap) -- "If the operating-mode file is
missing, invalid, or ambiguous, fail closed to an explicit current Owner lane
decision rather than guessing." -- and the file's own
``fail_closed.missing_invalid_or_ambiguous_mode: REQUIRE_EXPLICIT_CURRENT_OWNER_LANE``.

This module is read-only. It never selects a lane on failure: any status other
than ``VALID`` carries ``default_execution: None`` and at least one typed reason.
It does not select a CapabilityPlanner route, worker, model, verifier, approval,
integration, release, or production authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import yaml

SCHEMA = "nexus.operating_mode_check.v1"
STATUS_VALID = "VALID"
STATUS_DECISION_REQUIRED = "OWNER_LANE_DECISION_REQUIRED"

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PATH = Path("docs/governance/current_operating_mode.yaml")

EXPECTED_FILE_SCHEMA = "nexus.operating_mode.v1"
# AGENTS.md "Current self-hosting stabilization semantics" and
# docs/agents/TASK_EXECUTION_CONTRACT.md name only `BOOTSTRAP`. Owner-only
# NEXUS_GOVERNANCE_DEFAULT_READY is a transition decision, not a mode value, and
# requires a separate policy change (post_decision_effect) before it may appear.
KNOWN_MODES = frozenset({"BOOTSTRAP"})
LANES = ("DIRECT_CANONICAL", "DIRECT_DELEGATED", "GOVERNED")
DEFAULT_EXECUTION_KEYS = ("primary_bounded_work", "delegated_bounded_work")
REQUIRED_FAIL_CLOSED = "REQUIRE_EXPLICIT_CURRENT_OWNER_LANE"
REQUIRED_SILENT_DOWNGRADE = "FORBIDDEN"

# The v1 schema is closed: exactly the top-level keys of the checked-in file.
# An unrecognised key could carry lane semantics this validator cannot see, so
# it is treated as ambiguous rather than ignored.
KNOWN_TOP_LEVEL_KEYS = frozenset({
    "schema",
    "mode",
    "effective_scope",
    "default_execution",
    "lane_selection_basis",
    "protected_merge",
    "task_card_required_by_default",
    "auto_chain",
    "transition",
    "readiness_for_nexus_governance_default",
    "escalate_to_governed_when",
    "fail_closed",
    "principles",
})

# Keys (as dotted paths) whose values this validator evaluates; used by the
# drift-guard test against the real file.
EVALUATED_KEY_PATHS = (
    "schema",
    "mode",
    "default_execution.primary_bounded_work",
    "default_execution.delegated_bounded_work",
    "protected_merge.DIRECT_CANONICAL",
    "protected_merge.DIRECT_DELEGATED",
    "protected_merge.GOVERNED",
    "fail_closed.missing_invalid_or_ambiguous_mode",
    "transition.silent_governed_to_direct_downgrade",
    "auto_chain",
    "escalate_to_governed_when",
)

# Typed reason codes.
MODE_FILE_MISSING = "MODE_FILE_MISSING"
MODE_FILE_UNREADABLE = "MODE_FILE_UNREADABLE"
MODE_FILE_NOT_UTF8 = "MODE_FILE_NOT_UTF8"
YAML_PARSE_ERROR = "YAML_PARSE_ERROR"
DUPLICATE_KEY = "DUPLICATE_KEY"
TOP_LEVEL_NOT_MAPPING = "TOP_LEVEL_NOT_MAPPING"
UNKNOWN_TOP_LEVEL_KEY = "UNKNOWN_TOP_LEVEL_KEY"
SCHEMA_MISMATCH = "SCHEMA_MISMATCH"
UNKNOWN_MODE = "UNKNOWN_MODE"
DEFAULT_EXECUTION_INVALID = "DEFAULT_EXECUTION_INVALID"
DEFAULT_LANE_MISSING = "DEFAULT_LANE_MISSING"
DEFAULT_LANE_INVALID = "DEFAULT_LANE_INVALID"
DEFAULT_EXECUTION_UNKNOWN_KEY = "DEFAULT_EXECUTION_UNKNOWN_KEY"
PROTECTED_MERGE_INVALID = "PROTECTED_MERGE_INVALID"
PROTECTED_MERGE_LANE_MISSING = "PROTECTED_MERGE_LANE_MISSING"
PROTECTED_MERGE_UNKNOWN_LANE = "PROTECTED_MERGE_UNKNOWN_LANE"
FAIL_CLOSED_RULE_INVALID = "FAIL_CLOSED_RULE_INVALID"
SILENT_DOWNGRADE_NOT_FORBIDDEN = "SILENT_DOWNGRADE_NOT_FORBIDDEN"
AUTO_CHAIN_NOT_FALSE = "AUTO_CHAIN_NOT_FALSE"
ESCALATION_LIST_INVALID = "ESCALATION_LIST_INVALID"

REASON_CODES = (
    MODE_FILE_MISSING,
    MODE_FILE_UNREADABLE,
    MODE_FILE_NOT_UTF8,
    YAML_PARSE_ERROR,
    DUPLICATE_KEY,
    TOP_LEVEL_NOT_MAPPING,
    UNKNOWN_TOP_LEVEL_KEY,
    SCHEMA_MISMATCH,
    UNKNOWN_MODE,
    DEFAULT_EXECUTION_INVALID,
    DEFAULT_LANE_MISSING,
    DEFAULT_LANE_INVALID,
    DEFAULT_EXECUTION_UNKNOWN_KEY,
    PROTECTED_MERGE_INVALID,
    PROTECTED_MERGE_LANE_MISSING,
    PROTECTED_MERGE_UNKNOWN_LANE,
    FAIL_CLOSED_RULE_INVALID,
    SILENT_DOWNGRADE_NOT_FORBIDDEN,
    AUTO_CHAIN_NOT_FALSE,
    ESCALATION_LIST_INVALID,
)


class _DuplicateKeyError(yaml.YAMLError):
    """Raised when a YAML mapping repeats a key or uses a merge key."""


class _StrictLoader(yaml.SafeLoader):
    """SafeLoader that rejects duplicate keys and merge keys at every level."""


def _construct_strict_mapping(loader: _StrictLoader, node: yaml.MappingNode) -> dict[Any, Any]:
    seen: set[Any] = set()
    for key_node, _ in node.value:
        if key_node.tag == "tag:yaml.org,2002:merge":
            raise _DuplicateKeyError(f"merge key '<<' is ambiguous at {key_node.start_mark}")
        key = loader.construct_object(key_node, deep=True)
        try:
            duplicate = key in seen
        except TypeError as exc:
            raise _DuplicateKeyError(f"unhashable key at {key_node.start_mark}") from exc
        if duplicate:
            raise _DuplicateKeyError(f"duplicate key {key!r} at {key_node.start_mark}")
        seen.add(key)
    return loader.construct_mapping(node, deep=True)


_StrictLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_strict_mapping,  # type: ignore[arg-type]
)


def _reason(code: str, detail: str) -> dict[str, str]:
    return {"code": code, "detail": detail}


def _result(
    reasons: list[dict[str, str]],
    default_execution: dict[str, str] | None,
    source_sha256: str | None,
) -> dict[str, Any]:
    if default_execution is None and not reasons:
        # Defensive: a result without a lane selection is never VALID.
        reasons = [_reason(DEFAULT_EXECUTION_INVALID, "no lane selection could be derived")]
    valid = not reasons
    return {
        "schema": SCHEMA,
        "status": STATUS_VALID if valid else STATUS_DECISION_REQUIRED,
        "reasons": list(reasons),
        "default_execution": dict(default_execution) if valid and default_execution else None,
        "source_sha256": source_sha256,
    }


def _check_default_execution(
    doc: dict[Any, Any], reasons: list[dict[str, str]]
) -> dict[str, str] | None:
    raw = doc.get("default_execution")
    if not isinstance(raw, dict):
        reasons.append(_reason(DEFAULT_EXECUTION_INVALID, "default_execution must be a mapping"))
        return None
    selection: dict[str, str] = {}
    for key in DEFAULT_EXECUTION_KEYS:
        if key not in raw:
            reasons.append(_reason(DEFAULT_LANE_MISSING, f"default_execution.{key} is missing"))
            continue
        value = raw[key]
        if not isinstance(value, str) or value not in LANES:
            reasons.append(
                _reason(
                    DEFAULT_LANE_INVALID,
                    f"default_execution.{key}={value!r} is not one of {list(LANES)}",
                )
            )
            continue
        selection[key] = value
    for key in raw:
        if key not in DEFAULT_EXECUTION_KEYS:
            reasons.append(
                _reason(DEFAULT_EXECUTION_UNKNOWN_KEY, f"default_execution has unknown key {key!r}")
            )
    if len(selection) != len(DEFAULT_EXECUTION_KEYS):
        return None
    return selection


def _check_protected_merge(doc: dict[Any, Any], reasons: list[dict[str, str]]) -> None:
    raw = doc.get("protected_merge")
    if not isinstance(raw, dict):
        reasons.append(_reason(PROTECTED_MERGE_INVALID, "protected_merge must be a mapping"))
        return
    for lane in LANES:
        if not isinstance(raw.get(lane), dict) or not raw[lane]:
            reasons.append(
                _reason(
                    PROTECTED_MERGE_LANE_MISSING,
                    f"protected_merge.{lane} is missing or not a non-empty mapping",
                )
            )
    for lane in raw:
        if lane not in LANES:
            reasons.append(
                _reason(PROTECTED_MERGE_UNKNOWN_LANE, f"protected_merge has unknown lane {lane!r}")
            )


def _check_contract(doc: dict[Any, Any]) -> tuple[list[dict[str, str]], dict[str, str] | None]:
    reasons: list[dict[str, str]] = []
    for key in doc:
        if key not in KNOWN_TOP_LEVEL_KEYS:
            reasons.append(
                _reason(UNKNOWN_TOP_LEVEL_KEY, f"unknown top-level key {key!r} is ambiguous")
            )
    if doc.get("schema") != EXPECTED_FILE_SCHEMA:
        reasons.append(
            _reason(
                SCHEMA_MISMATCH,
                f"schema={doc.get('schema')!r}, expected {EXPECTED_FILE_SCHEMA!r}",
            )
        )
    mode = doc.get("mode")
    if not isinstance(mode, str) or mode not in KNOWN_MODES:
        reasons.append(_reason(UNKNOWN_MODE, f"mode={mode!r} is not one of {sorted(KNOWN_MODES)}"))
    selection = _check_default_execution(doc, reasons)
    _check_protected_merge(doc, reasons)

    fail_closed = doc.get("fail_closed")
    rule = (
        fail_closed.get("missing_invalid_or_ambiguous_mode")
        if isinstance(fail_closed, dict)
        else None
    )
    if rule != REQUIRED_FAIL_CLOSED:
        reasons.append(
            _reason(
                FAIL_CLOSED_RULE_INVALID,
                f"fail_closed.missing_invalid_or_ambiguous_mode={rule!r}, "
                f"expected {REQUIRED_FAIL_CLOSED!r}",
            )
        )

    transition = doc.get("transition")
    downgrade = (
        transition.get("silent_governed_to_direct_downgrade")
        if isinstance(transition, dict)
        else None
    )
    if downgrade != REQUIRED_SILENT_DOWNGRADE:
        reasons.append(
            _reason(
                SILENT_DOWNGRADE_NOT_FORBIDDEN,
                f"transition.silent_governed_to_direct_downgrade={downgrade!r}, "
                f"expected {REQUIRED_SILENT_DOWNGRADE!r}",
            )
        )

    auto_chain = doc.get("auto_chain", None)
    if auto_chain is not False:
        reasons.append(
            _reason(AUTO_CHAIN_NOT_FALSE, f"auto_chain={auto_chain!r}, expected boolean false")
        )

    escalate = doc.get("escalate_to_governed_when")
    if (
        not isinstance(escalate, list)
        or not escalate
        or not all(isinstance(item, str) and item.strip() for item in escalate)
    ):
        reasons.append(
            _reason(
                ESCALATION_LIST_INVALID,
                "escalate_to_governed_when must be a non-empty list of non-empty strings",
            )
        )
    return reasons, selection


def evaluate_operating_mode(path: str | Path) -> dict[str, Any]:
    """Evaluate the operating-mode file; never select a lane unless fully valid."""
    mode_path = Path(path)
    try:
        raw = mode_path.read_bytes()
    except FileNotFoundError:
        return _result([_reason(MODE_FILE_MISSING, f"{mode_path} does not exist")], None, None)
    except OSError as exc:
        return _result(
            [_reason(MODE_FILE_UNREADABLE, f"{mode_path}: {type(exc).__name__}: {exc}")],
            None,
            None,
        )
    digest = hashlib.sha256(raw).hexdigest()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return _result([_reason(MODE_FILE_NOT_UTF8, str(exc))], None, digest)
    try:
        loader = _StrictLoader(text)
        try:
            doc = loader.get_single_data()
        finally:
            loader.dispose()
    except _DuplicateKeyError as exc:
        return _result([_reason(DUPLICATE_KEY, str(exc))], None, digest)
    except yaml.YAMLError as exc:
        return _result([_reason(YAML_PARSE_ERROR, str(exc))], None, digest)
    if not isinstance(doc, dict):
        return _result(
            [_reason(TOP_LEVEL_NOT_MAPPING, f"top level is {type(doc).__name__}")],
            None,
            digest,
        )
    reasons, selection = _check_contract(doc)
    return _result(reasons, selection, digest)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument(
        "--path",
        default=None,
        help=f"operating-mode file (default: <repo>/{DEFAULT_PATH.as_posix()})",
    )
    args = parser.parse_args(argv)
    path = Path(args.path) if args.path else REPO_ROOT / DEFAULT_PATH
    result = evaluate_operating_mode(path)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == STATUS_VALID else 2


if __name__ == "__main__":
    sys.exit(main())
