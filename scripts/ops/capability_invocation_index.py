from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping

from nexus.engine.capability_aliases import normalize_capability_name
from nexus.engine.capability_wiring_audit import unused_reason_for_row


def _bool(value: Any) -> bool:
    return bool(value)


def empty_capability_cell() -> dict[str, Any]:
    return {
        "selected": False,
        "invoked": False,
        "evidence_present": False,
        "gate_passed": False,
        "outcome_contributed": False,
        "public_safe": False,
        "tasks": [],
        "unused_reasons": [],
        "selection_sources": [],
    }


def merge_capability_cell(cell: dict[str, Any], *, task_id: str, receipt: Mapping[str, Any]) -> None:
    cell["selected"] = cell["selected"] or _bool(receipt.get("selected"))
    cell["invoked"] = cell["invoked"] or _bool(receipt.get("invoked"))
    cell["evidence_present"] = cell["evidence_present"] or _bool(
        receipt.get("evidence_present") or receipt.get("evidence")
    )
    cell["gate_passed"] = cell["gate_passed"] or _bool(receipt.get("gate_passed") or receipt.get("gate"))
    cell["outcome_contributed"] = cell["outcome_contributed"] or _bool(receipt.get("outcome_contributed"))
    cell["public_safe"] = cell["public_safe"] or _bool(receipt.get("public_claim_safe"))
    if task_id and task_id not in cell["tasks"]:
        cell["tasks"].append(task_id)
    source = str(receipt.get("selection_source") or "").strip()
    if source and source not in cell["selection_sources"]:
        cell["selection_sources"].append(source)
    reason = unused_reason_for_row(
        {
            "selected": receipt.get("selected", False),
            "adapter_exists": True,
            "pending_executor": False,
            "maturity": "production",
            "invoked": receipt.get("invoked", False),
            "evidence_present": receipt.get("evidence_present") or receipt.get("evidence"),
            "gate_passed": receipt.get("gate_passed") or receipt.get("gate"),
            "outcome_contributed": receipt.get("outcome_contributed", False),
        }
    )
    if reason and reason not in cell["unused_reasons"]:
        cell["unused_reasons"].append(reason)


@dataclass(frozen=True)
class CapabilityInvocationArmIndex:
    rows: int
    expected: set[str] = field(default_factory=set)
    public_safe: set[str] = field(default_factory=set)
    capabilities: dict[str, dict[str, Any]] = field(default_factory=dict)
    failures: list[dict[str, Any]] = field(default_factory=list)
    diagnostics: list[dict[str, Any]] = field(default_factory=list)

    def to_arm_payload(self, *, name: str, path: str) -> dict[str, Any]:
        return {
            "arm": name,
            "path": path,
            "kind": "jsonl",
            "rows": self.rows,
            "expected_capabilities": sorted(self.expected),
            "public_safe_capabilities": sorted(self.public_safe),
            "capabilities": self.capabilities,
            "failures": self.failures,
            "diagnostics": self.diagnostics,
            "passed": bool(self.rows) and not self.failures,
        }


def build_arm_index(rows: list[Mapping[str, Any]]) -> CapabilityInvocationArmIndex:
    capabilities: dict[str, dict[str, Any]] = {}
    expected: set[str] = set()
    public_safe: set[str] = set()
    failures: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    for row in rows:
        task_id = str(row.get("task_id") or "")
        coverage = row.get("expected_capability_receipt_coverage") or {}
        for cap in coverage.get("expected", []) or []:
            normalized = normalize_capability_name(cap)
            if normalized:
                expected.add(normalized)
                capabilities.setdefault(normalized, empty_capability_cell())
        for cap in coverage.get("public_safe", []) or []:
            normalized = normalize_capability_name(cap)
            if normalized:
                public_safe.add(normalized)
        receipts = _coerce_receipts(row.get("capability_receipts") or [])
        for receipt in receipts:
            cap = normalize_capability_name(receipt.get("name") or receipt.get("capability"))
            if not cap:
                continue
            cell = capabilities.setdefault(cap, empty_capability_cell())
            merge_capability_cell(cell, task_id=task_id, receipt=receipt)
        for cap in coverage.get("expected", []) or []:
            normalized = normalize_capability_name(cap)
            cell = capabilities.get(normalized, empty_capability_cell()) if normalized else empty_capability_cell()
            if not normalized:
                continue
            if not cell.get("selected") or not cell.get("invoked") or not cell.get("evidence_present"):
                failures.append(
                    {
                        "task_id": task_id,
                        "kind": "expected_capability_not_invoked_with_evidence",
                        "capability": normalized,
                        "selected": bool(cell.get("selected")),
                        "invoked": bool(cell.get("invoked")),
                        "evidence_present": bool(cell.get("evidence_present")),
                        "failure_reason": (coverage.get("failure_reasons") or {}).get(normalized),
                    }
                )
            elif not cell.get("public_safe"):
                diagnostics.append(
                    {
                        "task_id": task_id,
                        "kind": "expected_capability_invoked_but_not_public_safe",
                        "capability": normalized,
                        "gate_passed": bool(cell.get("gate_passed")),
                        "outcome_contributed": bool(cell.get("outcome_contributed")),
                        "failure_reason": (coverage.get("failure_reasons") or {}).get(normalized),
                    }
                )
        if not str(row.get("route_decision_schema_version") or "").strip():
            failures.append({"task_id": task_id, "kind": "route_decision_missing"})
    return CapabilityInvocationArmIndex(
        rows=len(rows),
        expected=expected,
        public_safe=public_safe,
        capabilities=capabilities,
        failures=failures,
        diagnostics=diagnostics,
    )


def _coerce_receipts(raw_receipts: Any) -> list[Mapping[str, Any]]:
    receipts = raw_receipts
    if isinstance(receipts, str):
        try:
            receipts = json.loads(receipts)
        except json.JSONDecodeError:
            receipts = []
    return [receipt for receipt in receipts if isinstance(receipt, Mapping)] if isinstance(receipts, list) else []
