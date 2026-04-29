from __future__ import annotations

from typing import Any

from nexus.engine.capability_contracts import CapabilityPlan, CapabilityReceipt
from nexus.engine.capability_receipt_adapters import RECEIPT_ADAPTERS, merge_capability_receipt


def _selected_capabilities(plan: CapabilityPlan | dict[str, Any]) -> list[str]:
    return plan.selected_capabilities if isinstance(plan, CapabilityPlan) else plan.get("selected_capabilities", []) or []


def _pending_capabilities(plan: CapabilityPlan | dict[str, Any]) -> set[str]:
    pending = plan.pending_capabilities if isinstance(plan, CapabilityPlan) else plan.get("pending_capabilities", []) or []
    return {str(name) for name in pending}


def _pending_receipt(name: str, receipt: CapabilityReceipt | None = None) -> CapabilityReceipt:
    return merge_capability_receipt(
        name=name,
        selected=False,
        invoked=bool(receipt.invoked) if receipt else False,
        evidence_refs=receipt.evidence_refs if receipt else (),
        gate_passed=bool(receipt.gate_passed) if receipt else False,
        outcome_contributed=False,
        executor_id=receipt.executor_id if receipt else name,
        failure_reason="pending_executor",
    )


def selected_receipts(plan: CapabilityPlan | dict[str, Any]) -> list[CapabilityReceipt]:
    pending = _pending_capabilities(plan)
    receipts = []
    for name in _selected_capabilities(plan):
        capability = str(name)
        receipts.append(_pending_receipt(capability) if capability in pending else CapabilityReceipt(name=capability, selected=True))
    return receipts


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
    selected = set(_selected_capabilities(plan))
    pending = _pending_capabilities(plan)
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
            receipt = adapter.build(claim_verified=claim_verified, payload=payload)
            if name in pending and not receipt.public_claim_safe:
                receipts.append(_pending_receipt(name, receipt))
                continue
            receipts.append(receipt)
            continue
        receipts.append(_pending_receipt(name) if name in pending else CapabilityReceipt(name=name, selected=True))
    return receipts
