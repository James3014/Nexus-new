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


# --- Claim-boundary attestation (Nexus-new side) -------------------------------------------
#
# The pinned nexus-runtime ``CapabilityReceipt.to_dict()`` hands ``project_child_receipt_base``
# a fixed claim boundary without ``simulated``, so ``ClaimBoundary`` defaults it to true for
# every receipt.  The runtime offers no hook (``to_dict`` takes no argument and ``from_dict``
# does not exist), so Nexus-new re-projects ``receipt_base`` with an evaluated boundary.
# The runtime producer still needs a fix (``to_dict`` should accept a claim boundary); this is
# the Nexus-new-side post-processing step until it lands.

_NON_EXECUTION_ACTIONS = frozenset({
    "auth_gate",
    "skip",
    "resolve",
    "probe",
    "fixture",
    "construct",
})


def _outcome_evidence_refs(receipt: Any, outcome: Any) -> list[str]:
    refs = [str(r) for r in (getattr(receipt, "evidence_refs", ()) or ()) if str(r).strip()]
    evidence_id = str(getattr(receipt, "evidence_id", "") or "").strip()
    if evidence_id:
        refs.append(evidence_id)
    if isinstance(outcome, dict):
        refs.extend(str(r) for r in (outcome.get("evidence_refs") or []) if str(r).strip())
    return list(dict.fromkeys(refs))


def evaluate_receipt_claim_boundary(
    receipt: Any, executor_outcome: dict[str, Any] | None = None
) -> Any:
    """Evaluate the claim boundary for one capability receipt (fail-closed).

    ``simulated`` is False only when the receipt reports a real invocation, evidence refs exist,
    and the executor outcome is not an auth block, skip, import/construct-only result, or error.
    ``public_claim_allowed`` stays False regardless (``ClaimBoundary.evaluate`` never unlocks it).
    """
    from nexus_runtime.planning.evidence.claim_boundary import evaluate_claim_boundary

    outcome = (
        executor_outcome if executor_outcome is not None else getattr(receipt, "outcome", None)
    )
    outcome = outcome if isinstance(outcome, dict) else {}
    refs = _outcome_evidence_refs(receipt, outcome)
    invoked = bool(getattr(receipt, "invoked", False))
    action = str(outcome.get("action") or "")
    real = (
        invoked
        and bool(refs)
        and action not in _NON_EXECUTION_ACTIONS
        and str(outcome.get("error") or "") != "import_construct_not_execution"
        and not outcome.get("auth_required")
        and str(outcome.get("semantic_status") or "").upper() not in {"BLOCKED", "SKIPPED"}
    )
    telemetries = getattr(receipt, "telemetries", None)
    try:
        model_calls = int((telemetries or {}).get("model_calls") or 0)
    except (TypeError, ValueError):
        model_calls = 0
    return evaluate_claim_boundary(
        simulated=not real,
        claim_eligible=bool(real and getattr(receipt, "gate_passed", False)),
        receipt_present=bool(refs),
        model_calls=model_calls,
    )


def attested_receipt_dict(
    receipt: Any, executor_outcome: dict[str, Any] | None = None
) -> dict[str, Any]:
    """``receipt.to_dict()`` with ``receipt_base`` re-projected under an evaluated boundary."""
    base = receipt.to_dict()
    try:
        boundary = evaluate_receipt_claim_boundary(receipt, executor_outcome)
        from nexus_runtime.planning.evidence.receipt_base import project_child_receipt_base

        name = str(
            getattr(receipt, "name", "") or getattr(receipt, "capability_name", "") or "capability"
        )
        old = base.get("receipt_base") if isinstance(base.get("receipt_base"), dict) else {}
        refs = _outcome_evidence_refs(receipt, executor_outcome)
        invoked = bool(getattr(receipt, "invoked", False))
        gate_passed = bool(getattr(receipt, "gate_passed", False))
        contributed = getattr(receipt, "outcome_contributed", None)
        if contributed is None:
            contributed = bool(invoked and gate_passed and getattr(receipt, "outcome", None))
        base["receipt_base"] = project_child_receipt_base(
            source_world=str(old.get("source_world") or "B"),
            source_component=str(old.get("source_component") or "capability_receipt_engine"),
            task_id=str(old.get("task_id") or ""),
            stage_payload={
                "name": name,
                "selected": bool(getattr(receipt, "selected", False)),
                "invoked": invoked,
                "gate_passed": gate_passed,
                "outcome_contributed": bool(contributed),
                "executor_id": str(getattr(receipt, "executor_id", "") or ""),
            },
            stage_name=name,
            evidence_refs=refs,
            consumer=str((old.get("consumption_chain") or [{}])[0].get("consumer") or "engine"),
            selected=bool(getattr(receipt, "selected", False)),
            injected=invoked,
            used=bool(invoked and contributed),
            evidence_present=bool(refs),
            gate_passed=gate_passed,
            outcome_contributed=bool(contributed),
            claim_boundary=boundary.to_dict(),
        )
        base.pop("receipt_base_error", None)
    except Exception as exc:  # noqa: BLE001 - keep the unattested (simulated=true) projection
        base["receipt_base_attestation_error"] = str(exc)[:200]
    return base


def build_attested_trace_receipts(
    *,
    executor_outcomes: dict[str, dict[str, Any]] | None = None,
    **kwargs: Any,
) -> list[dict[str, Any]]:
    """``build_trace_receipts`` + attestation; no outcome for a capability means simulated=true."""
    outcomes = executor_outcomes or {}
    return [
        attested_receipt_dict(
            item, outcomes.get(normalize_capability_name(str(getattr(item, "name", ""))))
        )
        for item in build_trace_receipts(**kwargs)
    ]
