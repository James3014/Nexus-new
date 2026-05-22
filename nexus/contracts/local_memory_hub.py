from __future__ import annotations

from typing import Any, Mapping


LOCAL_MEMORY_HUB_SCHEMA = "nexus.local_memory_hub.v1"


def build_local_memory_hub_snapshot(
    *,
    capabilities: list[str] | tuple[str, ...],
    evidence_root: str,
    budget: Mapping[str, Any] | None = None,
    recent_receipts: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...] = (),
) -> dict[str, Any]:
    blockers: list[str] = []
    clean_receipts = [
        receipt
        for receipt in recent_receipts
        if str(receipt.get("status") or "").upper() in {"PASS", "NOT_APPLICABLE"}
    ]
    if not evidence_root.strip():
        blockers.append("missing_evidence_root")
    if len(clean_receipts) != len(recent_receipts):
        blockers.append("recent_receipt_not_clean")
    capability_list = sorted({str(item).strip() for item in capabilities if str(item).strip()})
    if not capability_list:
        blockers.append("missing_capabilities")
    return {
        "schema": LOCAL_MEMORY_HUB_SCHEMA,
        "status": "PASS" if not blockers else "RETURN",
        "capabilities": capability_list,
        "health": "HEALTHY" if not blockers else "DEGRADED",
        "budget": dict(budget or {}),
        "evidence_root": evidence_root,
        "recent_receipt_count": len(recent_receipts),
        "clean_receipt_count": len(clean_receipts),
        "mutable_global_singleton": False,
        "distributed_heartbeat_required": False,
        "blockers": sorted(set(blockers)),
        "runtime_update_allowed": False,
        "public_benchmark_allowed": False,
    }
