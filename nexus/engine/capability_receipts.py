from __future__ import annotations

from typing import Any

from nexus.engine.capability_aliases import normalize_capability_name, normalize_capability_names
from nexus.engine.capability_contracts import CapabilityPlan, CapabilityReceipt, SkillReceipt
from nexus.engine.capability_receipt_adapters import RECEIPT_ADAPTERS, merge_capability_receipt


def _selected_capabilities(plan: CapabilityPlan | dict[str, Any]) -> list[str]:
    selected = plan.selected_capabilities if isinstance(plan, CapabilityPlan) else plan.get("selected_capabilities", []) or []
    return normalize_capability_names(selected)


def _pending_capabilities(plan: CapabilityPlan | dict[str, Any]) -> set[str]:
    pending = plan.pending_capabilities if isinstance(plan, CapabilityPlan) else plan.get("pending_capabilities", []) or []
    return set(normalize_capability_names(pending))


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
        capability = normalize_capability_name(name)
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
        name = normalize_capability_name(name)
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


def build_skill_receipts(
    *,
    skills: list[dict[str, Any]] | None = None,
    injected_ids: set[str] | tuple[str, ...] | list[str] | None = None,
    used_ids: set[str] | tuple[str, ...] | list[str] | None = None,
    evidence_ids: set[str] | tuple[str, ...] | list[str] | None = None,
    outcome_ids: set[str] | tuple[str, ...] | list[str] | None = None,
) -> list[SkillReceipt]:
    injected = {str(item) for item in (injected_ids or [])}
    used = {str(item) for item in (used_ids or [])}
    evidence = {str(item) for item in (evidence_ids or [])}
    outcome = {str(item) for item in (outcome_ids or [])}
    receipts: list[SkillReceipt] = []
    for skill in skills or []:
        skill_id = str(skill.get("skill_id") or skill.get("task_id") or "").strip()
        if not skill_id:
            continue
        selected = bool(skill.get("selected", True))
        was_injected = skill_id in injected or bool(skill.get("injected", False))
        was_used = skill_id in used or bool(skill.get("used", False))
        has_evidence = skill_id in evidence or bool(skill.get("evidence_present", False))
        contributed = skill_id in outcome or bool(skill.get("outcome_contributed", False))
        failure_reason = ""
        if selected and not was_injected:
            failure_reason = "selected_without_injection"
        elif selected and was_used and not has_evidence:
            failure_reason = "used_without_evidence"
        receipts.append(
            SkillReceipt(
                skill_id=skill_id,
                selected=selected,
                injected=was_injected,
                used=was_used,
                evidence_present=has_evidence,
                outcome_contributed=bool(contributed and has_evidence),
                failure_reason=failure_reason,
            )
        )
    return receipts
