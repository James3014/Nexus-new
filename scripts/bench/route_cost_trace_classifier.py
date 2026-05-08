from __future__ import annotations

import json
from typing import Any


HIGH_COST_CAPABILITIES = {
    "research",
    "external_doc_scout",
    "ultra_review",
    "sandbox",
    "swarm",
    "nightshift",
    "research_control_plane",
}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _receipt_capability(receipt: dict[str, Any]) -> str:
    return str(receipt.get("name") or receipt.get("capability") or "").strip()


def _receipt_refs(receipt: dict[str, Any]) -> list[str]:
    refs = receipt.get("evidence_refs", receipt.get("evidence", []))
    if isinstance(refs, str):
        return [refs]
    return [str(item) for item in _as_list(refs) if str(item).strip()]


def _ref_kinds(refs: list[str]) -> list[str]:
    kinds: set[str] = set()
    for ref in refs:
        parts = ref.split(":")
        if len(parts) >= 3:
            kinds.add(parts[-1])
        elif ref:
            kinds.add(ref)
    return sorted(kinds)


def _receipt_bool(receipt: dict[str, Any], key: str) -> bool:
    return bool(receipt.get(key, False))


def _capability_receipts(row: dict[str, Any]) -> list[dict[str, Any]]:
    receipts = row.get("capability_receipts")
    if isinstance(receipts, list):
        return [item for item in receipts if isinstance(item, dict)]
    raw = row.get("capability_receipts_json")
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except ValueError:
            return []
        return [item for item in parsed if isinstance(item, dict)] if isinstance(parsed, list) else []
    return []


def _selected_high_cost(row: dict[str, Any]) -> list[str]:
    selected = [str(item) for item in _as_list(row.get("route_profile_high_cost_selected")) if str(item).strip()]
    if selected:
        return sorted(set(selected))
    plan_selected = [str(item) for item in _as_list(row.get("capability_plan_selected")) if str(item).strip()]
    return sorted({item for item in plan_selected if item in HIGH_COST_CAPABILITIES})


def classify_high_cost_capability_trace(row: dict[str, Any]) -> list[dict[str, Any]]:
    receipts = _capability_receipts(row)
    receipts_by_capability = {_receipt_capability(receipt): receipt for receipt in receipts}
    out: list[dict[str, Any]] = []
    for capability in _selected_high_cost(row):
        receipt = receipts_by_capability.get(capability, {})
        refs = _receipt_refs(receipt)
        kinds = _ref_kinds(refs)
        selected = True
        invoked = _receipt_bool(receipt, "invoked")
        evidence_present = _receipt_bool(receipt, "evidence_present") or bool(refs)
        outcome_contributed = _receipt_bool(receipt, "outcome_contributed")
        substantive_evidence_present = evidence_present and any(kind != "route_selected" for kind in kinds)
        substantive_outcome_contributed = outcome_contributed and substantive_evidence_present
        if not receipt:
            classification = "missing_receipt"
        elif not invoked:
            classification = "selected_not_invoked"
        elif not evidence_present:
            classification = "invoked_without_evidence"
        elif not substantive_evidence_present:
            classification = "route_selected_only_evidence"
        elif not outcome_contributed:
            classification = "evidence_without_outcome"
        else:
            classification = "contributed"
        out.append(
            {
                "capability": capability,
                "selected": selected,
                "invoked": invoked,
                "evidence_present": evidence_present,
                "substantive_evidence_present": substantive_evidence_present,
                "outcome_contributed": outcome_contributed,
                "substantive_outcome_contributed": substantive_outcome_contributed,
                "evidence_ref_count": len(refs),
                "evidence_ref_kinds": kinds,
                "classification": classification,
            }
        )
    return out


def build_route_cost_trace_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    traced_rows = []
    classification_counts: dict[str, int] = {}
    wasted_count = 0
    for row in rows:
        traces = classify_high_cost_capability_trace(row)
        if not traces:
            continue
        for trace in traces:
            classification = str(trace["classification"])
            classification_counts[classification] = classification_counts.get(classification, 0) + 1
            if classification != "contributed":
                wasted_count += 1
        traced_rows.append(
            {
                "mode": str(row.get("mode") or ""),
                "task_id": str(row.get("task_id") or ""),
                "trial_index": row.get("trial_index"),
                "high_cost_trace": traces,
            }
        )
    return {
        "schema": "nexus_route_cost_trace_report_v1",
        "rows_with_high_cost": len(traced_rows),
        "wasted_high_cost_count": wasted_count,
        "classification_counts": dict(sorted(classification_counts.items())),
        "rows": traced_rows,
    }
