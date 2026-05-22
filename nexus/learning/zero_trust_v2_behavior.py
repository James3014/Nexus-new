from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


REQUIRED_BEHAVIOR_FIELDS = (
    "selected",
    "injected",
    "used",
    "evidence_present",
    "gate_passed",
    "outcome_contributed",
    "trust_mismatch",
)


def _walk_dicts(value: Any) -> list[Mapping[str, Any]]:
    found: list[Mapping[str, Any]] = []
    if isinstance(value, Mapping):
        found.append(value)
        for child in value.values():
            found.extend(_walk_dicts(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(_walk_dicts(child))
    return found


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "pass", "passed"}
    return bool(value)


def extract_behavior_receipt_from_bundle(bundle: Mapping[str, Any], *, skill_id: str = "") -> dict[str, Any]:
    merged: dict[str, Any] = {}
    matching_dicts = []
    for item in _walk_dicts(bundle):
        if skill_id and skill_id not in json.dumps(item, ensure_ascii=False):
            continue
        if any(field in item for field in REQUIRED_BEHAVIOR_FIELDS):
            matching_dicts.append(item)
            for field in REQUIRED_BEHAVIOR_FIELDS:
                if field in item and field not in merged:
                    merged[field] = item[field]
    missing = [field for field in REQUIRED_BEHAVIOR_FIELDS if field not in merged]
    failed: list[str] = [f"MISSING_BEHAVIOR_FIELD:{field}" for field in missing]
    for field in ("selected", "injected", "used", "evidence_present", "gate_passed", "outcome_contributed"):
        if field in merged and not _truthy(merged[field]):
            failed.append(f"BEHAVIOR_FIELD_FALSE:{field}")
    if _truthy(merged.get("trust_mismatch")):
        failed.append("TRUST_MISMATCH_NONZERO")
    return {
        "status": "PASS" if not failed else "BLOCKED",
        "observed_fields": {field: merged.get(field) for field in REQUIRED_BEHAVIOR_FIELDS if field in merged},
        "missing_fields": missing,
        "failed_security_contract_rules": sorted(set(failed)),
        "matched_receipt_fragment_count": len(matching_dicts),
    }


def extract_behavior_receipt_from_path(path: str | Path, *, skill_id: str = "") -> dict[str, Any]:
    source = Path(path)
    if not source.exists():
        return {
            "status": "BLOCKED",
            "observed_fields": {},
            "missing_fields": list(REQUIRED_BEHAVIOR_FIELDS),
            "failed_security_contract_rules": ["EVIDENCE_BUNDLE_NOT_FOUND"],
            "matched_receipt_fragment_count": 0,
        }
    try:
        bundle = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {
            "status": "BLOCKED",
            "observed_fields": {},
            "missing_fields": list(REQUIRED_BEHAVIOR_FIELDS),
            "failed_security_contract_rules": ["EVIDENCE_BUNDLE_INVALID_JSON"],
            "matched_receipt_fragment_count": 0,
        }
    return extract_behavior_receipt_from_bundle(bundle, skill_id=skill_id)


def build_behavior_runner_command_spec(item: Mapping[str, Any]) -> dict[str, Any]:
    capability_id = str(item.get("capability_id") or "")
    skill_id = str(item.get("skill_id") or "")
    return {
        "capability_id": capability_id,
        "skill_id": skill_id,
        "runner_kind": "capability_ab_runner",
        "command": [
            "uv",
            "run",
            "python",
            "scripts/bench/capability_ab_runner.py",
            "--nexus-only",
            "--with-nexus-runner",
            "subprocess",
            "--with-llm-mode",
            "all",
        ],
        "requires_selected_capability_scope": capability_id,
        "requires_skill_mount_request": skill_id,
        "promotion_credit_allowed": False,
        "blocked_reason": "command_spec_only_until_physical_behavior_runner_executes",
    }
