from __future__ import annotations

from typing import Any, Protocol

from nexus.engine.capability_contracts import CapabilityReceipt


class CapabilityReceiptAdapter(Protocol):
    name: str

    def build(self, *, claim_verified: bool, payload: dict[str, Any]) -> CapabilityReceipt:
        ...


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


def as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def selected_failure_reason(*, selected: bool, invoked: bool, evidence_refs: list[str], gate_passed: bool) -> str:
    if not selected:
        return ""
    if not invoked:
        return "selected_without_invocation"
    if not evidence_refs:
        return "invoked_without_evidence"
    if not gate_passed:
        return "evidence_without_gate_pass"
    return ""


class CodeIntelReceiptAdapter:
    name = "codeintel"

    def build(self, *, claim_verified: bool, payload: dict[str, Any]) -> CapabilityReceipt:
        refs = [payload.get("scan_report_path"), payload.get("impact_report_path")]
        invoked = bool(payload.get("scan_report_present") or payload.get("impact_report_present"))
        gate_passed = bool(payload.get("impact_report_present") and payload.get("claim_bundle_present"))
        return merge_capability_receipt(
            name=self.name,
            selected=True,
            invoked=invoked,
            evidence_refs=refs,
            gate_passed=gate_passed,
            outcome_contributed=bool(gate_passed and claim_verified),
            executor_id=self.name,
        )


class AutoreasonReceiptAdapter:
    name = "autoreason"

    def build(self, *, claim_verified: bool, payload: dict[str, Any]) -> CapabilityReceipt:
        refs = [payload.get("winner")] + [str(item) for item in (payload.get("judge_votes", []) or [])]
        clean_refs = [
            str(item).strip()
            for item in refs
            if item is not None and str(item).strip() and str(item).strip() != "None"
        ]
        invoked = bool(payload.get("enabled") or payload.get("status"))
        gate_passed = bool(payload.get("winner") and claim_verified)
        return merge_capability_receipt(
            name=self.name,
            selected=True,
            invoked=invoked,
            evidence_refs=refs,
            gate_passed=gate_passed,
            outcome_contributed=bool(gate_passed and claim_verified),
            executor_id=self.name,
            failure_reason=selected_failure_reason(
                selected=True,
                invoked=invoked,
                evidence_refs=clean_refs,
                gate_passed=gate_passed,
            ),
        )


class DDTreeReceiptAdapter:
    name = "ddtree"

    def build(self, *, claim_verified: bool, payload: dict[str, Any]) -> CapabilityReceipt:
        refs = [str(item) for item in (payload.get("selected_candidate_ids", []) or [])]
        saved_steps = as_int(payload.get("actual_saved_steps", 0))
        if saved_steps > 0:
            refs.append(f"saved_steps:{saved_steps}")
        invoked = bool(payload.get("enabled") and payload.get("eligible"))
        gate_passed = bool(saved_steps > 0 and claim_verified)
        return merge_capability_receipt(
            name=self.name,
            selected=True,
            invoked=invoked,
            evidence_refs=refs,
            gate_passed=gate_passed,
            outcome_contributed=bool(gate_passed and claim_verified),
            executor_id=self.name,
        )


class UltraReviewReceiptAdapter:
    name = "ultra_review"

    def build(self, *, claim_verified: bool, payload: dict[str, Any]) -> CapabilityReceipt:
        invoked = bool(payload.get("invoked", False))
        gate_passed = bool(payload.get("gate_passed", False))
        report_path = str(payload.get("report_path") or "").strip()
        if not invoked and payload.get("reason"):
            failure_reason = str(payload.get("reason") or "")
        else:
            failure_reason = selected_failure_reason(
                selected=True,
                invoked=invoked,
                evidence_refs=[report_path] if report_path else [],
                gate_passed=gate_passed,
            )
        return merge_capability_receipt(
            name=self.name,
            selected=True,
            invoked=invoked,
            evidence_refs=[report_path],
            gate_passed=gate_passed,
            outcome_contributed=bool(gate_passed and claim_verified),
            executor_id=self.name,
            failure_reason=failure_reason,
        )


class SwarmReceiptAdapter:
    name = "swarm"

    def build(self, *, claim_verified: bool, payload: dict[str, Any]) -> CapabilityReceipt:
        report = payload.get("swarm_report") if isinstance(payload.get("swarm_report"), dict) else {}
        evidence_count = as_int(report.get("evidence_count", payload.get("swarm_evidence_count", 0)))
        invoked = bool(payload.get("swarm_used", False))
        refs = [str(item) for item in report.get("evidence_refs", []) or [] if str(item).strip()]
        if report.get("report_path"):
            refs.append(f"report:{report.get('report_path')}")
        if evidence_count > 0:
            refs.append(f"role_findings:{evidence_count}")
        consensus = report.get("consensus") or payload.get("swarm_consensus")
        if consensus:
            refs.append(f"consensus:{consensus}")
        gate_passed = bool(evidence_count > 0 and claim_verified)
        return merge_capability_receipt(
            name=self.name,
            selected=True,
            invoked=invoked,
            evidence_refs=refs,
            gate_passed=gate_passed,
            outcome_contributed=bool(gate_passed and claim_verified),
            executor_id=self.name,
            failure_reason=selected_failure_reason(
                selected=True,
                invoked=invoked,
                evidence_refs=refs,
                gate_passed=gate_passed,
            ),
        )


class DroneReceiptAdapter:
    name = "drone"

    def build(self, *, claim_verified: bool, payload: dict[str, Any]) -> CapabilityReceipt:
        report = payload.get("drone_report") if isinstance(payload.get("drone_report"), dict) else {}
        invoked_count = as_int(report.get("artifact_count", payload.get("drone_invoked_count", 0)))
        invoked = bool(payload.get("drone_used", False) or invoked_count > 0)
        refs = [f"artifact:{item}" for item in report.get("artifact_paths", []) or [] if str(item).strip()]
        if report.get("report_path"):
            refs.append(f"report:{report.get('report_path')}")
        if invoked_count > 0:
            refs.append(f"subtask_artifact:{invoked_count}")
        if payload.get("drone_artifact_path"):
            refs.append(f"artifact:{payload.get('drone_artifact_path')}")
        gate_passed = bool(invoked_count > 0 and claim_verified)
        return merge_capability_receipt(
            name=self.name,
            selected=True,
            invoked=invoked,
            evidence_refs=refs,
            gate_passed=gate_passed,
            outcome_contributed=bool(gate_passed and claim_verified),
            executor_id=self.name,
            failure_reason=selected_failure_reason(
                selected=True,
                invoked=invoked,
                evidence_refs=refs,
                gate_passed=gate_passed,
            ),
        )


class NightshiftReceiptAdapter:
    name = "nightshift"

    def build(self, *, claim_verified: bool, payload: dict[str, Any]) -> CapabilityReceipt:
        report = payload.get("nightshift_report") if isinstance(payload.get("nightshift_report"), dict) else {}
        invoked = bool(report.get("invoked", payload.get("nightshift_invoked", False)))
        recovered = bool(report.get("recovered", payload.get("nightshift_recovered", False)))
        report_path = str(report.get("report_path") or payload.get("nightshift_report_path") or "").strip()
        refs = [report_path] if report_path else []
        recommended = bool(report.get("recommended", payload.get("nightshift_recommended", False)))
        if recommended and not invoked:
            failure_reason = str(report.get("failure_reason") or payload.get("nightshift_failure_reason") or "recommended_without_invocation")
        else:
            failure_reason = selected_failure_reason(
                selected=True,
                invoked=invoked,
                evidence_refs=refs,
                gate_passed=recovered,
            )
        if report.get("failure_reason"):
            failure_reason = str(report.get("failure_reason"))
        return merge_capability_receipt(
            name=self.name,
            selected=True,
            invoked=invoked,
            evidence_refs=refs,
            gate_passed=recovered,
            outcome_contributed=bool(recovered and claim_verified),
            executor_id=self.name,
            failure_reason=failure_reason,
        )


RECEIPT_ADAPTERS: dict[str, CapabilityReceiptAdapter] = {
    adapter.name: adapter
    for adapter in (
        CodeIntelReceiptAdapter(),
        AutoreasonReceiptAdapter(),
        DDTreeReceiptAdapter(),
        UltraReviewReceiptAdapter(),
        SwarmReceiptAdapter(),
        DroneReceiptAdapter(),
        NightshiftReceiptAdapter(),
    )
}
