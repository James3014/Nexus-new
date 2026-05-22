from __future__ import annotations

import json
from typing import Any

from nexus.engine.capability_aliases import (
    normalize_capability_name,
    normalize_capability_names,
    normalize_capability_receipt,
)
from nexus.engine.capability_receipt_policy import expected_capability_receipt_coverage


def receipt_data_contract(row: dict[str, Any]) -> dict[str, Any]:
    if str(row.get("mode") or "") != "with_nexus":
        return {"status": "NOT_APPLICABLE", "missing": [], "reason": "non_nexus_arm"}
    coverage = row.get("expected_capability_receipt_coverage")
    coverage = coverage if isinstance(coverage, dict) else {}
    missing = [str(item) for item in coverage.get("missing", []) or [] if str(item).strip()]
    return {
        "status": "DATA_CONTRACT_VIOLATION" if missing else "PASS",
        "missing": missing,
        "reason": "missing_expected_capability_receipts" if missing else "",
    }


def expected_capability_invocation_coverage(
    expected_capabilities: tuple[str, ...],
    capability_receipts: list[dict[str, Any]],
) -> dict[str, Any]:
    receipts = {
        normalize_capability_name(item.get("name") or item.get("capability")): normalize_capability_receipt(item)
        for item in capability_receipts
        if isinstance(item, dict) and str(item.get("name") or item.get("capability") or "").strip()
    }
    expected = normalize_capability_names(expected_capabilities)
    invoked: list[str] = []
    missing: list[str] = []
    failure_reasons: dict[str, str] = {}
    for capability in expected:
        receipt = receipts.get(capability)
        if not receipt:
            missing.append(capability)
            failure_reasons[capability] = "missing_receipt"
            continue
        if (
            bool(receipt.get("selected"))
            and bool(receipt.get("invoked"))
            and bool(receipt.get("evidence_present"))
        ):
            invoked.append(capability)
            continue
        missing.append(capability)
        if not bool(receipt.get("selected")):
            failure_reasons[capability] = "not_selected"
        elif not bool(receipt.get("invoked")):
            failure_reasons[capability] = "not_invoked"
        else:
            failure_reasons[capability] = "missing_evidence"
    return {
        "expected": expected,
        "invoked": invoked,
        "missing": missing,
        "failure_reasons": failure_reasons,
        "all_invoked_with_evidence": bool(expected) and not missing,
    }


def build_row_receipt_fields(
    *,
    expected_capabilities: tuple[str, ...],
    capability_receipts: list[dict[str, Any]],
    skill_mount_contract: list[dict[str, Any]],
    skill_mount_contract_status: str,
    skill_mount_violations: list[dict[str, Any]],
) -> dict[str, Any]:
    receipt_dicts = [item for item in capability_receipts if isinstance(item, dict)]
    return {
        "capability_receipts": capability_receipts,
        "capability_receipts_json": json.dumps(capability_receipts, ensure_ascii=False, sort_keys=True),
        "skill_mount_contract": skill_mount_contract,
        "skill_mount_contract_json": json.dumps(skill_mount_contract, ensure_ascii=False, sort_keys=True),
        "skill_mount_count": len(skill_mount_contract),
        "skill_mount_contract_status": skill_mount_contract_status,
        "skill_mount_violations": skill_mount_violations,
        "skill_mount_violations_json": json.dumps(skill_mount_violations, ensure_ascii=False, sort_keys=True),
        "expected_capability_receipt_coverage": expected_capability_receipt_coverage(
            expected_capabilities=expected_capabilities,
            capability_receipts=receipt_dicts,
        ),
        "expected_capability_invocation_coverage": expected_capability_invocation_coverage(
            expected_capabilities,
            receipt_dicts,
        ),
    }
