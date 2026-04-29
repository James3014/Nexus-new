from __future__ import annotations

from typing import Any

from nexus.engine.capability_contracts import CapabilityPlan, CapabilityReceipt
from nexus.engine.capability_receipt_adapters import RECEIPT_ADAPTERS, merge_capability_receipt


def selected_receipts(plan: CapabilityPlan | dict[str, Any]) -> list[CapabilityReceipt]:
    selected = plan.selected_capabilities if isinstance(plan, CapabilityPlan) else plan.get("selected_capabilities", []) or []
    return [CapabilityReceipt(name=str(name), selected=True) for name in selected]


def build_trace_receipts(
    *,
    plan: CapabilityPlan | dict[str, Any],
    capabilities: dict[str, Any] | None = None,
    autoreason: dict[str, Any] | None = None,
    ddtree: dict[str, Any] | None = None,
    ultra_review: dict[str, Any] | None = None,
    codeintel: dict[str, Any] | None = None,
) -> list[CapabilityReceipt]:
    capabilities = capabilities or {}
    autoreason = autoreason or {}
    ddtree = ddtree or {}
    ultra_review = ultra_review or {}
    codeintel = codeintel or {}
    selected = set(plan.selected_capabilities if isinstance(plan, CapabilityPlan) else plan.get("selected_capabilities", []) or [])
    claim_verified = bool(capabilities.get("claim_verified", False))
    receipts: list[CapabilityReceipt] = []

    for name in sorted(selected):
        adapter = RECEIPT_ADAPTERS.get(name)
        if adapter:
            payload = {
                "codeintel": codeintel,
                "autoreason": autoreason,
                "ddtree": ddtree,
                "ultra_review": ultra_review,
            }.get(name, capabilities)
            receipts.append(adapter.build(claim_verified=claim_verified, payload=payload))
            continue
        receipts.append(CapabilityReceipt(name=name, selected=True))
    return receipts
