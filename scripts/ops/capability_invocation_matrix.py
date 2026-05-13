#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from nexus.engine.capability_aliases import normalize_capability_name
from nexus.engine.capability_receipt_policy import REQUIRED_ROUTE_RUNTIME_CAPABILITIES
from nexus.engine.capability_wiring_audit import build_capability_wiring_audit, unused_reason_for_row


@dataclass(frozen=True)
class ArmInput:
    name: str
    path: Path


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _bool(value: Any) -> bool:
    return bool(value)


def _empty_cell() -> dict[str, Any]:
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


def _merge_cell(cell: dict[str, Any], *, task_id: str, receipt: dict[str, Any]) -> None:
    cell["selected"] = cell["selected"] or _bool(receipt.get("selected"))
    cell["invoked"] = cell["invoked"] or _bool(receipt.get("invoked"))
    cell["evidence_present"] = cell["evidence_present"] or _bool(receipt.get("evidence_present") or receipt.get("evidence"))
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


def _integrity_heatmap_entry(capability: str, item: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    if item.get("ever_selected") and not item.get("ever_invoked"):
        reasons.append("selected_no_invoked")
    if item.get("ever_invoked") and not item.get("ever_evidence"):
        reasons.append("invoked_no_evidence")
    if item.get("ever_evidence") and not item.get("ever_public_safe"):
        reasons.append("evidence_not_public_safe")
    if item.get("ever_public_safe") and not item.get("ever_outcome"):
        reasons.append("public_safe_no_outcome")
    if item.get("pending_executor") and item.get("ever_public_safe"):
        reasons.append("pending_executor_public_safe_claim")
    if not item.get("ever_selected") and item.get("required_runtime"):
        reasons.append("required_never_selected")

    if any(reason in reasons for reason in {"required_never_selected", "selected_no_invoked", "invoked_no_evidence"}):
        severity = "red"
    elif reasons:
        severity = "yellow"
    else:
        severity = "green"
    return {
        "capability": capability,
        "severity": severity,
        "reasons": reasons or ["healthy"],
    }


def _cell_integrity_heatmap_entry(capability: str, arm: dict[str, Any], cell: dict[str, Any]) -> dict[str, Any]:
    expected = capability in set(arm.get("expected_capabilities", []) or [])
    item = {
        "required_runtime": expected,
        "pending_executor": False,
        "ever_selected": bool(cell.get("selected")),
        "ever_invoked": bool(cell.get("invoked")),
        "ever_evidence": bool(cell.get("evidence_present")),
        "ever_outcome": bool(cell.get("outcome_contributed")),
        "ever_public_safe": bool(cell.get("public_safe")),
    }
    return _integrity_heatmap_entry(capability, item)


def _arm_from_jsonl(name: str, path: Path) -> dict[str, Any]:
    rows = _load_jsonl(path)
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
                capabilities.setdefault(normalized, _empty_cell())
        for cap in coverage.get("public_safe", []) or []:
            normalized = normalize_capability_name(cap)
            if normalized:
                public_safe.add(normalized)
        receipts = row.get("capability_receipts") or []
        if isinstance(receipts, str):
            try:
                receipts = json.loads(receipts)
            except json.JSONDecodeError:
                receipts = []
        for receipt in receipts if isinstance(receipts, list) else []:
            if not isinstance(receipt, dict):
                continue
            cap = normalize_capability_name(receipt.get("name") or receipt.get("capability"))
            if not cap:
                continue
            cell = capabilities.setdefault(cap, _empty_cell())
            _merge_cell(cell, task_id=task_id, receipt=receipt)
        for cap in coverage.get("expected", []) or []:
            normalized = normalize_capability_name(cap)
            cell = capabilities.get(normalized, _empty_cell()) if normalized else _empty_cell()
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
    return {
        "arm": name,
        "path": str(path),
        "kind": "jsonl",
        "rows": len(rows),
        "expected_capabilities": sorted(expected),
        "public_safe_capabilities": sorted(public_safe),
        "capabilities": capabilities,
        "failures": failures,
        "diagnostics": diagnostics,
        "passed": bool(rows) and not failures,
    }


def _arm_from_smoke_summary(name: str, path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    capabilities: dict[str, dict[str, Any]] = {}
    expected: set[str] = set()
    public_safe: set[str] = set()
    failures = list(payload.get("failures", []) or [])
    for suite in payload.get("suites", []) or []:
        suite_name = str(suite.get("suite") or "")
        for cap in suite.get("expected_capabilities", []) or []:
            normalized = normalize_capability_name(cap)
            if normalized:
                expected.add(normalized)
                capabilities.setdefault(normalized, _empty_cell())
        for cap in suite.get("public_safe_capabilities", []) or []:
            normalized = normalize_capability_name(cap)
            if not normalized:
                continue
            public_safe.add(normalized)
            cell = capabilities.setdefault(normalized, _empty_cell())
            receipt = {
                "selected": True,
                "invoked": True,
                "evidence_present": True,
                "gate_passed": True,
                "outcome_contributed": True,
                "public_claim_safe": True,
            }
            _merge_cell(cell, task_id=suite_name, receipt=receipt)
    return {
        "arm": name,
        "path": str(path),
        "kind": "smoke_summary",
        "rows": sum(int(suite.get("tasks", 0) or 0) for suite in payload.get("suites", []) or []),
        "expected_capabilities": sorted(expected),
        "public_safe_capabilities": sorted(public_safe),
        "capabilities": capabilities,
        "failures": failures,
        "passed": bool(payload.get("passed")) and not failures,
    }


def _load_arm(raw: str) -> ArmInput:
    if ":" not in raw:
        raise ValueError("--arm must use NAME:PATH")
    name, path = raw.split(":", 1)
    return ArmInput(name=name.strip(), path=Path(path).expanduser())


def _arm_payload(arm: ArmInput) -> dict[str, Any]:
    path = arm.path if arm.path.is_absolute() else REPO_ROOT / arm.path
    if not path.exists():
        return {
            "arm": arm.name,
            "path": str(path),
            "kind": "missing",
            "rows": 0,
            "expected_capabilities": [],
            "public_safe_capabilities": [],
            "capabilities": {},
            "failures": [{"kind": "arm_file_missing", "path": str(path)}],
            "passed": False,
        }
    if path.suffix == ".json" and "capability_route_smoke_summary" in path.name:
        return _arm_from_smoke_summary(arm.name, path)
    return _arm_from_jsonl(arm.name, path)


def _executor_spec_for(wiring_rows: dict[str, dict[str, Any]], cap: str) -> dict[str, Any]:
    row = wiring_rows.get(cap) or {}
    spec = row.get("executor_spec") if isinstance(row, dict) else {}
    return spec if isinstance(spec, dict) else {}


def _combine_matrix(
    arms: list[dict[str, Any]],
    required: set[str],
    *,
    wiring_rows: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    wiring_rows = wiring_rows or {}
    matrix: dict[str, Any] = {}
    all_caps = set(required)
    for arm in arms:
        all_caps.update(str(cap) for cap in (arm.get("capabilities") or {}).keys())
    for cap in sorted(all_caps):
        wiring_row = wiring_rows.get(cap) or {}
        executor_spec = _executor_spec_for(wiring_rows, cap)
        per_arm = {}
        ever_selected = ever_invoked = ever_evidence = ever_outcome = ever_public_safe = False
        for arm in arms:
            cell = (arm.get("capabilities") or {}).get(cap, _empty_cell())
            cell["integrity_heatmap"] = _cell_integrity_heatmap_entry(cap, arm, cell)
            per_arm[arm["arm"]] = cell
            ever_selected = ever_selected or bool(cell.get("selected"))
            ever_invoked = ever_invoked or bool(cell.get("invoked"))
            ever_evidence = ever_evidence or bool(cell.get("evidence_present"))
            ever_outcome = ever_outcome or bool(cell.get("outcome_contributed"))
            ever_public_safe = ever_public_safe or bool(cell.get("public_safe"))
        matrix[cap] = {
            "required_runtime": cap in required,
            "wiring_status": str(wiring_row.get("status") or ""),
            "pending_executor": bool(wiring_row.get("pending_executor", False)),
            "runtime_claim_allowed": bool(executor_spec.get("runtime_claim_allowed", True)),
            "allowed_claim_scope": str(executor_spec.get("allowed_claim_scope") or ""),
            "ever_selected": ever_selected,
            "ever_invoked": ever_invoked,
            "ever_evidence": ever_evidence,
            "ever_outcome": ever_outcome,
            "ever_public_safe": ever_public_safe,
            "selection_sources": sorted(
                {
                    str(source)
                    for cell in per_arm.values()
                    for source in (cell.get("selection_sources") or [])
                    if str(source).strip()
                }
            ),
            "arms": per_arm,
        }
        matrix[cap]["integrity_heatmap"] = _integrity_heatmap_entry(cap, matrix[cap])
        arm_heatmaps = [
            cell.get("integrity_heatmap", {})
            for cell in per_arm.values()
            if isinstance(cell.get("integrity_heatmap"), dict)
        ]
        if any(item.get("severity") == "red" for item in arm_heatmaps):
            matrix[cap]["integrity_heatmap"]["severity"] = "red"
            matrix[cap]["integrity_heatmap"]["reasons"] = sorted(
                {
                    str(reason)
                    for item in arm_heatmaps
                    if item.get("severity") == "red"
                    for reason in (item.get("reasons") or [])
                }
            )
        elif any(item.get("severity") == "yellow" for item in arm_heatmaps):
            matrix[cap]["integrity_heatmap"]["severity"] = "yellow"
            matrix[cap]["integrity_heatmap"]["reasons"] = sorted(
                {
                    str(reason)
                    for item in arm_heatmaps
                    if item.get("severity") == "yellow"
                    for reason in (item.get("reasons") or [])
                }
            )
    return matrix


def _render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Nexus Capability Invocation Matrix",
        "",
        f"- schema: `{payload.get('schema_version')}`",
        f"- passed: `{payload.get('passed')}`",
        "",
        "## Integrity Heatmap",
        "",
        "| capability | severity | reasons |",
        "| --- | --- | --- |",
    ]
    for cap, item in sorted((payload.get("matrix") or {}).items()):
        heatmap = item.get("integrity_heatmap", {}) if isinstance(item, dict) else {}
        reasons = ", ".join(str(reason) for reason in heatmap.get("reasons", []) or [])
        lines.append(f"| `{cap}` | `{heatmap.get('severity', '')}` | {reasons} |")
    lines.append("")
    return "\n".join(lines)


def build_invocation_matrix(*, arms: list[ArmInput], required: set[str] | None = None) -> dict[str, Any]:
    required = set(required or REQUIRED_ROUTE_RUNTIME_CAPABILITIES)
    arm_payloads = [_arm_payload(arm) for arm in arms]
    wiring = build_capability_wiring_audit().to_dict()
    wiring_rows = {
        str(row.get("name")): row
        for row in wiring.get("rows", [])
        if isinstance(row, dict) and str(row.get("name") or "")
    }
    matrix = _combine_matrix(arm_payloads, required, wiring_rows=wiring_rows)
    failures: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    if not wiring["passed"]:
        failures.append(
            {
                "kind": "wiring_audit_failed",
                "high_priority_registry_only": wiring["high_priority_registry_only"],
                "high_priority_missing_receipt_policy": wiring["high_priority_missing_receipt_policy"],
            }
        )
    for arm in arm_payloads:
        if not arm.get("passed"):
            failures.append({"kind": "arm_failed", "arm": arm.get("arm"), "failures": arm.get("failures", [])})
    for cap in sorted(required):
        item = matrix.get(cap) or {}
        missing = [
            key
            for key, field in (
                ("never_selected", "ever_selected"),
                ("never_invoked", "ever_invoked"),
                ("never_evidence", "ever_evidence"),
                ("never_outcome", "ever_outcome"),
                ("never_public_safe", "ever_public_safe"),
            )
            if not item.get(field)
        ]
        if missing:
            failures.append({"kind": "required_runtime_capability_gap", "capability": cap, "gaps": missing})
        elif item.get("pending_executor") and item.get("ever_public_safe"):
            diagnostics.append(
                {
                    "kind": "pending_executor_receipt_or_shadow_claim_scope",
                    "capability": cap,
                    "wiring_status": item.get("wiring_status"),
                    "allowed_claim_scope": item.get("allowed_claim_scope"),
                }
            )
    model_arms = [arm for arm in arm_payloads if arm.get("kind") == "jsonl"]
    for arm in model_arms:
        if not arm.get("expected_capabilities"):
            failures.append({"kind": "model_arm_no_expected_capability", "arm": arm.get("arm")})
    return {
        "schema_version": "nexus_capability_invocation_matrix.v1",
        "required_runtime_capabilities": sorted(required),
        "arms": arm_payloads,
        "matrix": matrix,
        "wiring_audit": wiring,
        "diagnostics": diagnostics,
        "failures": failures,
        "passed": not failures,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a three-arm Nexus capability invocation matrix.")
    parser.add_argument("--arm", action="append", default=[], help="Arm input as NAME:PATH")
    parser.add_argument("--output", default="", help="Optional JSON output path")
    parser.add_argument("--markdown-output", default="", help="Optional Markdown heatmap output path")
    args = parser.parse_args(argv)
    arms = [_load_arm(item) for item in args.arm]
    payload = build_invocation_matrix(arms=arms)
    if args.output:
        output = Path(args.output)
        output = output if output.is_absolute() else REPO_ROOT / output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        payload["output"] = str(output)
    if args.markdown_output:
        markdown_output = Path(args.markdown_output)
        markdown_output = markdown_output if markdown_output.is_absolute() else REPO_ROOT / markdown_output
        markdown_output.parent.mkdir(parents=True, exist_ok=True)
        markdown_output.write_text(_render_markdown(payload), encoding="utf-8")
        payload["markdown_output"] = str(markdown_output)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
