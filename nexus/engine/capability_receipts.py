from __future__ import annotations

from typing import Any

from nexus.engine.capability_contracts import CapabilityPlan, CapabilityReceipt


def selected_receipts(plan: CapabilityPlan | dict[str, Any]) -> list[CapabilityReceipt]:
    selected = plan.selected_capabilities if isinstance(plan, CapabilityPlan) else plan.get("selected_capabilities", []) or []
    return [CapabilityReceipt(name=str(name), selected=True) for name in selected]


def merge_capability_receipt(
    *,
    name: str,
    selected: bool,
    invoked: bool = False,
    evidence_refs: list[str] | tuple[str, ...] | None = None,
    gate_passed: bool = False,
    outcome_contributed: bool = False,
    executor_id: str = "",
    failure_reason: str = "",
) -> CapabilityReceipt:
    refs = tuple(
        text
        for item in (evidence_refs or ())
        if item is not None
        for text in (str(item).strip(),)
        if text and text != "None"
    )
    return CapabilityReceipt(
        name=name,
        selected=selected,
        invoked=invoked,
        evidence_present=bool(refs),
        gate_passed=gate_passed,
        outcome_contributed=outcome_contributed,
        executor_id=executor_id,
        evidence_refs=refs,
        failure_reason=failure_reason,
    )


def _first_present(*values: Any) -> str:
    for value in values:
        if value:
            return str(value)
    return ""


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _selected_failure_reason(*, selected: bool, invoked: bool, evidence_refs: list[str], gate_passed: bool) -> str:
    if not selected:
        return ""
    if not invoked:
        return "selected_without_invocation"
    if not evidence_refs:
        return "invoked_without_evidence"
    if not gate_passed:
        return "evidence_without_gate_pass"
    return ""


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
        if name == "codeintel":
            refs = [codeintel.get("scan_report_path"), codeintel.get("impact_report_path")]
            invoked = bool(codeintel.get("scan_report_present") or codeintel.get("impact_report_present"))
            gate_passed = bool(codeintel.get("impact_report_present") and codeintel.get("claim_bundle_present"))
            receipts.append(
                merge_capability_receipt(
                    name=name,
                    selected=True,
                    invoked=invoked,
                    evidence_refs=refs,
                    gate_passed=gate_passed,
                    outcome_contributed=bool(gate_passed and claim_verified),
                    executor_id="codeintel",
                )
            )
            continue
        if name == "autoreason":
            refs = [autoreason.get("winner")] + [str(item) for item in (autoreason.get("judge_votes", []) or [])]
            invoked = bool(autoreason.get("enabled") or autoreason.get("status"))
            gate_passed = bool(autoreason.get("winner") and claim_verified)
            receipts.append(
                merge_capability_receipt(
                    name=name,
                    selected=True,
                    invoked=invoked,
                    evidence_refs=refs,
                    gate_passed=gate_passed,
                    outcome_contributed=bool(gate_passed and claim_verified),
                    executor_id="autoreason",
                    failure_reason=_selected_failure_reason(
                        selected=True,
                        invoked=invoked,
                        evidence_refs=[
                            str(item).strip()
                            for item in refs
                            if item is not None and str(item).strip() and str(item).strip() != "None"
                        ],
                        gate_passed=gate_passed,
                    ),
                )
            )
            continue
        if name == "ddtree":
            refs = [str(item) for item in (ddtree.get("selected_candidate_ids", []) or [])]
            if int(ddtree.get("actual_saved_steps", 0) or 0) > 0:
                refs.append(f"saved_steps:{int(ddtree.get('actual_saved_steps', 0) or 0)}")
            invoked = bool(ddtree.get("enabled") and ddtree.get("eligible"))
            gate_passed = bool(int(ddtree.get("actual_saved_steps", 0) or 0) > 0 and claim_verified)
            receipts.append(
                merge_capability_receipt(
                    name=name,
                    selected=True,
                    invoked=invoked,
                    evidence_refs=refs,
                    gate_passed=gate_passed,
                    outcome_contributed=bool(gate_passed and claim_verified),
                    executor_id="ddtree",
                )
            )
            continue
        if name == "ultra_review":
            invoked = bool(ultra_review.get("invoked", False))
            gate_passed = bool(ultra_review.get("gate_passed", False))
            receipts.append(
                merge_capability_receipt(
                    name=name,
                    selected=True,
                    invoked=invoked,
                    evidence_refs=[ultra_review.get("report_path")],
                    gate_passed=gate_passed,
                    outcome_contributed=bool(gate_passed and claim_verified),
                    executor_id="ultra_review",
                    failure_reason=str(ultra_review.get("reason") or "")
                    if not invoked and ultra_review.get("reason")
                    else _selected_failure_reason(
                        selected=True,
                        invoked=invoked,
                        evidence_refs=[str(ultra_review.get("report_path")).strip()]
                        if ultra_review.get("report_path")
                        else [],
                        gate_passed=gate_passed,
                    ),
                )
            )
            continue
        if name == "swarm":
            evidence_count = _as_int(capabilities.get("swarm_evidence_count", 0))
            invoked = bool(capabilities.get("swarm_used", False))
            refs = []
            if evidence_count > 0:
                refs.append(f"role_findings:{evidence_count}")
            if capabilities.get("swarm_consensus"):
                refs.append(f"consensus:{capabilities.get('swarm_consensus')}")
            gate_passed = bool(evidence_count > 0 and claim_verified)
            receipts.append(
                merge_capability_receipt(
                    name=name,
                    selected=True,
                    invoked=invoked,
                    evidence_refs=refs,
                    gate_passed=gate_passed,
                    outcome_contributed=bool(gate_passed and claim_verified),
                    executor_id="swarm",
                    failure_reason=_selected_failure_reason(
                        selected=True,
                        invoked=invoked,
                        evidence_refs=refs,
                        gate_passed=gate_passed,
                    ),
                )
            )
            continue
        if name == "drone":
            invoked_count = _as_int(capabilities.get("drone_invoked_count", 0))
            invoked = bool(capabilities.get("drone_used", False) or invoked_count > 0)
            refs = []
            if invoked_count > 0:
                refs.append(f"subtask_artifact:{invoked_count}")
            if capabilities.get("drone_artifact_path"):
                refs.append(f"artifact:{capabilities.get('drone_artifact_path')}")
            gate_passed = bool(invoked_count > 0 and claim_verified)
            receipts.append(
                merge_capability_receipt(
                    name=name,
                    selected=True,
                    invoked=invoked,
                    evidence_refs=refs,
                    gate_passed=gate_passed,
                    outcome_contributed=bool(gate_passed and claim_verified),
                    executor_id="drone",
                    failure_reason=_selected_failure_reason(
                        selected=True,
                        invoked=invoked,
                        evidence_refs=refs,
                        gate_passed=gate_passed,
                    ),
                )
            )
            continue
        if name == "nightshift":
            invoked = bool(capabilities.get("nightshift_invoked", False))
            recovered = bool(capabilities.get("nightshift_recovered", False))
            report_path = _first_present(capabilities.get("nightshift_report_path"))
            refs = [report_path] if report_path else []
            if capabilities.get("nightshift_recommended") and not invoked:
                failure_reason = str(capabilities.get("nightshift_failure_reason") or "recommended_without_invocation")
            else:
                failure_reason = _selected_failure_reason(
                    selected=True,
                    invoked=invoked,
                    evidence_refs=refs,
                    gate_passed=recovered,
                )
            receipts.append(
                merge_capability_receipt(
                    name=name,
                    selected=True,
                    invoked=invoked,
                    evidence_refs=refs,
                    gate_passed=recovered,
                    outcome_contributed=bool(recovered and claim_verified),
                    executor_id="nightshift",
                    failure_reason=failure_reason,
                )
            )
            continue
        receipts.append(CapabilityReceipt(name=name, selected=True))
    return receipts
