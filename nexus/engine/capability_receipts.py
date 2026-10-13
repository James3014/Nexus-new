from __future__ import annotations

from typing import Any

from nexus.engine.capability_aliases import normalize_capability_name, normalize_capability_names
from nexus.engine.capability_contracts import CapabilityPlan, CapabilityReceipt, SkillReceipt
from nexus.engine.capability_receipt_adapters import RECEIPT_ADAPTERS, merge_capability_receipt


def _selected_capabilities(plan: CapabilityPlan | dict[str, Any]) -> list[str]:
    selected = (
        plan.selected_capabilities
        if isinstance(plan, CapabilityPlan)
        else plan.get("selected_capabilities", []) or []
    )
    return normalize_capability_names(selected)


def _pending_capabilities(plan: CapabilityPlan | dict[str, Any]) -> set[str]:
    pending = (
        plan.pending_capabilities
        if isinstance(plan, CapabilityPlan)
        else plan.get("pending_capabilities", []) or []
    )
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
        receipts.append(
            _pending_receipt(capability)
            if capability in pending
            else CapabilityReceipt(name=capability, selected=True)
        )
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
        receipts.append(
            _pending_receipt(name)
            if name in pending
            else CapabilityReceipt(name=name, selected=True)
        )
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


# --- Claim-boundary attestation -----------------------------------------------------------
#
# Since nexus-runtime #187 (pinned 6782e38) ``CapabilityReceipt.to_dict()`` derives
# ``claim_boundary.simulated`` from the receipt's own execution evidence, so the runtime is the
# attestation authority.  Nexus-new only adds what the runtime cannot see from the receipt
# alone: the executor *outcome* (auth block, skip, construct-only, ...).  That extra input may
# only tighten the boundary (simulated false -> true), never loosen it.


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

    Delegates to the runtime evaluator (``attested_claim_boundary``) with the executor
    outcome attached.  ``public_claim_allowed`` stays False regardless.
    """
    from nexus_runtime.planning.evidence.claim_boundary import attested_claim_boundary

    outcome = (
        executor_outcome if executor_outcome is not None else getattr(receipt, "outcome", None)
    )
    outcome = outcome if isinstance(outcome, dict) else {}
    executor_id = getattr(receipt, "executor_id", None)
    telemetries = getattr(receipt, "telemetries", None)
    return attested_claim_boundary(
        invoked=bool(getattr(receipt, "invoked", False)),
        evidence_refs=_outcome_evidence_refs(receipt, outcome),
        gate_passed=bool(getattr(receipt, "gate_passed", False)),
        model_calls=telemetries.get("model_calls", 0) if isinstance(telemetries, dict) else 0,
        physical_callable=None if executor_id is None else str(executor_id),
        outcome=outcome,
        failure_reason=str(getattr(receipt, "failure_reason", "") or ""),
    )


def attested_receipt_dict(
    receipt: Any, executor_outcome: dict[str, Any] | None = None
) -> dict[str, Any]:
    """``receipt.to_dict()``; ``receipt_base`` is re-projected only to tighten the boundary.

    Fail-closed: only an explicit ``simulated is False`` set by the runtime producer
    (nexus-runtime #187) counts as real.  A runtime ``True`` is returned unchanged (Nexus-new
    can never flip it); a missing / null / non-bool ``simulated`` is re-projected as
    ``simulated=True, claim_eligible=False``; an executor outcome showing a non-execution the
    receipt alone could not see also tightens to ``simulated=True``.  Never loosens.
    """
    base = receipt.to_dict()
    old = base.get("receipt_base") if isinstance(base.get("receipt_base"), dict) else {}
    runtime_cb = old.get("claim_boundary") if isinstance(old.get("claim_boundary"), dict) else {}
    runtime_simulated = runtime_cb.get("simulated")
    if runtime_simulated is True:
        return base  # already fail-closed; nothing local may override it
    try:
        boundary = evaluate_receipt_claim_boundary(receipt, executor_outcome)
        if runtime_simulated is False and boundary.simulated is False:
            return base  # runtime attests a real execution and the outcome agrees
        from nexus_runtime.planning.evidence.claim_boundary import evaluate_claim_boundary
        from nexus_runtime.planning.evidence.receipt_base import project_child_receipt_base

        tightened = evaluate_claim_boundary(
            simulated=True,
            claim_eligible=False,
            receipt_present=runtime_cb.get("receipt_present") is True,
            model_calls=int(runtime_cb.get("model_calls") or 0),
        )
        name = str(getattr(receipt, "name", "") or "capability")
        invoked = bool(getattr(receipt, "invoked", False))
        gate_passed = bool(getattr(receipt, "gate_passed", False))
        contributed = bool(getattr(receipt, "outcome_contributed", False))
        refs = [str(r) for r in (getattr(receipt, "evidence_refs", ()) or ()) if str(r).strip()]
        base["receipt_base"] = project_child_receipt_base(
            source_world=str(old.get("source_world") or "B"),
            source_component=str(old.get("source_component") or "capability_receipt_engine"),
            task_id=str(old.get("task_id") or ""),
            stage_payload={
                "name": name,
                "selected": bool(getattr(receipt, "selected", False)),
                "invoked": invoked,
                "gate_passed": gate_passed,
                "outcome_contributed": contributed,
                "executor_id": str(getattr(receipt, "executor_id", "") or ""),
            },
            stage_name=name,
            evidence_refs=refs,
            consumer=str((old.get("consumption_chain") or [{}])[0].get("consumer") or "engine"),
            selected=bool(getattr(receipt, "selected", False)),
            injected=invoked,
            used=bool(invoked and contributed),
            evidence_present=bool(getattr(receipt, "evidence_present", bool(refs))),
            gate_passed=gate_passed,
            outcome_contributed=contributed,
            claim_boundary=tightened.to_dict(),
        )
    except Exception as exc:  # noqa: BLE001 - fail closed, record why
        base["receipt_base_attestation_error"] = str(exc)[:200]
        if isinstance(base.get("receipt_base"), dict):
            cb = dict(runtime_cb)
            cb.update(simulated=True, claim_eligible=False, public_claim_allowed=False)
            base["receipt_base"]["claim_boundary"] = cb
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
