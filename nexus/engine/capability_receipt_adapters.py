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


def _as_bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "pass", "passed", "verified"}
    return bool(value)


def _as_refs(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    if value is None:
        return []
    text = str(value).strip()
    return [text] if text else []


def _pillar_present(payload: dict[str, Any], *names: str) -> bool:
    pillars = payload.get("pillars") if isinstance(payload.get("pillars"), dict) else {}
    for name in names:
        if _as_bool(pillars.get(name)):
            return True
    return False


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
            failure_reason=selected_failure_reason(
                selected=True,
                invoked=invoked,
                evidence_refs=[str(item) for item in refs if str(item).strip()],
                gate_passed=gate_passed,
            ),
        )


class AutoreasonReceiptAdapter:
    name = "autoreason"

    def build(self, *, claim_verified: bool, payload: dict[str, Any]) -> CapabilityReceipt:
        winner = payload.get("winner") or payload.get("winner_id")
        status = str(payload.get("status") or "").strip().upper()
        disabled = status in {"DISABLED", "FEATURE_FLAG_DISABLED", "SKIPPED", "NOOP"}
        invoked = bool((payload.get("enabled") or status == "SUCCESS") and not disabled)
        refs: list[Any] = []
        if invoked:
            refs = [winner] + [str(item) for item in (payload.get("judge_votes", []) or payload.get("judge_scores", []) or [])]
            for key in ("incumbent_id", "stop_reason"):
                if payload.get(key):
                    refs.append(f"{key}:{payload.get(key)}")
        clean_refs = [
            str(item).strip()
            for item in refs
            if item is not None and str(item).strip() and str(item).strip() != "None"
        ]
        gate_passed = bool(winner and claim_verified)
        return merge_capability_receipt(
            name=self.name,
            selected=True,
            invoked=invoked,
            evidence_refs=refs,
            gate_passed=bool(invoked and gate_passed),
            outcome_contributed=bool(invoked and gate_passed and clean_refs),
            executor_id=self.name,
            failure_reason=selected_failure_reason(
                selected=True,
                invoked=invoked,
                evidence_refs=clean_refs,
                gate_passed=bool(invoked and gate_passed),
            ),
        )


class DDTreeReceiptAdapter:
    name = "ddtree"

    def build(self, *, claim_verified: bool, payload: dict[str, Any]) -> CapabilityReceipt:
        saved_steps = as_int(payload.get("actual_saved_steps", 0))
        candidate_count = as_int(payload.get("candidate_count", 0))
        max_candidates = as_int(payload.get("max_candidates", 0))
        refs: list[str] = []
        if saved_steps > 0:
            refs = [str(item) for item in (payload.get("selected_candidate_ids", []) or []) if str(item).strip()]
            refs.append(f"saved_steps:{saved_steps}")
            tree_stats = payload.get("tree_stats") if isinstance(payload.get("tree_stats"), dict) else {}
            if tree_stats:
                refs.extend(
                    [
                        f"tree_depth:{as_int(tree_stats.get('max_depth'))}",
                        f"branch_count:{as_int(tree_stats.get('branch_count'))}",
                        f"pruned_count:{as_int(tree_stats.get('pruned_count', saved_steps))}",
                    ]
                )
        clean_refs = [str(item).strip() for item in refs if str(item).strip()]
        invoked = bool(payload.get("enabled") and payload.get("eligible") and saved_steps > 0)
        gate_passed = bool(saved_steps > 0 and claim_verified)
        if not payload.get("enabled"):
            failure_reason = "feature_flag_disabled"
        elif not payload.get("eligible") or not invoked:
            failure_reason = "no_pruning_opportunity"
        else:
            failure_reason = selected_failure_reason(
                selected=True,
                invoked=invoked,
                evidence_refs=clean_refs,
                gate_passed=gate_passed,
            )
        return merge_capability_receipt(
            name=self.name,
            selected=True,
            invoked=invoked,
            evidence_refs=refs,
            gate_passed=gate_passed,
            outcome_contributed=bool(gate_passed and claim_verified),
            executor_id=self.name,
            failure_reason=failure_reason,
        )


class HyperReceiptAdapter:
    name = "hyper"

    def build(self, *, claim_verified: bool, payload: dict[str, Any]) -> CapabilityReceipt:
        invoked = bool(payload.get("hyper_used", False))
        refs: list[str] = []
        if invoked:
            refs.append(str(payload.get("winner_source") or "hyper_sprint"))
            if payload.get("attempt_count"):
                refs.append(f"attempt_count:{payload.get('attempt_count')}")
            if payload.get("self_heal_used"):
                refs.append("self_heal_used:true")
        gate_passed = bool(invoked and claim_verified)
        return merge_capability_receipt(
            name=self.name,
            selected=True,
            invoked=invoked,
            evidence_refs=refs,
            gate_passed=gate_passed,
            outcome_contributed=gate_passed,
            executor_id="hyper_sprint",
            failure_reason=selected_failure_reason(
                selected=True,
                invoked=invoked,
                evidence_refs=refs,
                gate_passed=gate_passed,
            ),
        )


class MemPalaceGateReceiptAdapter:
    name = "mempalace_gate"

    def build(self, *, claim_verified: bool, payload: dict[str, Any]) -> CapabilityReceipt:
        refs = _as_refs(payload.get("mempalace_audit_ref") or payload.get("mempalace_refs"))
        invoked = bool(_pillar_present(payload, "mempalace", "mempalace_gate") or refs)
        gate_passed = bool(refs and _as_bool(payload.get("mempalace_gate_passed", True)))
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


class ArtifactGateReceiptAdapter:
    name = "artifact_gate"

    def build(self, *, claim_verified: bool, payload: dict[str, Any]) -> CapabilityReceipt:
        invoked = bool(_pillar_present(payload, "artifact", "artifact_gate") or payload.get("artifact_refs"))
        refs = _as_refs(payload.get("artifact_refs") or payload.get("artifact_ref"))
        gate_passed = bool(refs and _as_bool(payload.get("artifact_gate_passed", True)))
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


class ClaimGateReceiptAdapter:
    name = "claim_gate"

    def build(self, *, claim_verified: bool, payload: dict[str, Any]) -> CapabilityReceipt:
        refs = _as_refs(payload.get("claim_refs") or payload.get("claim_ref"))
        invoked = bool(claim_verified or refs or payload.get("claim_gate_invoked"))
        gate_passed = bool(refs and claim_verified)
        return merge_capability_receipt(
            name=self.name,
            selected=True,
            invoked=invoked,
            evidence_refs=refs,
            gate_passed=gate_passed,
            outcome_contributed=gate_passed,
            executor_id=self.name,
            failure_reason=selected_failure_reason(
                selected=True,
                invoked=invoked,
                evidence_refs=refs,
                gate_passed=gate_passed,
            ),
        )


class DeliveryGateReceiptAdapter:
    name = "delivery_gate"

    def build(self, *, claim_verified: bool, payload: dict[str, Any]) -> CapabilityReceipt:
        refs = _as_refs(payload.get("delivery_refs") or payload.get("delivery_ref") or payload.get("evidence_bundle_path"))
        invoked = bool(payload.get("delivery_gate_passed") is not None or refs or payload.get("delivery_gate_invoked") or claim_verified)
        gate_passed = bool(refs and _as_bool(payload.get("delivery_gate_passed", claim_verified)))
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


class MemoryReceiptAdapter:
    name = "memory"

    def build(self, *, claim_verified: bool, payload: dict[str, Any]) -> CapabilityReceipt:
        hits = as_int(payload.get("memory_hits", payload.get("route_memory_hits", 0)))
        refs = _as_refs(payload.get("memory_refs") or payload.get("memory_ref"))
        invoked = bool(hits > 0 or refs or payload.get("memory_used"))
        gate_passed = bool(refs and _as_bool(payload.get("memory_gate_passed", False)))
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


class BeliefReceiptAdapter:
    name = "belief"

    def build(self, *, claim_verified: bool, payload: dict[str, Any]) -> CapabilityReceipt:
        refs = _as_refs(payload.get("belief_refs") or payload.get("belief_ref"))
        invoked = bool(payload.get("belief_confidence") is not None or refs or _pillar_present(payload, "belief"))
        gate_passed = bool(refs and _as_bool(payload.get("belief_gate_passed", False)))
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


class ResearchReceiptAdapter:
    name = "research"

    def build(self, *, claim_verified: bool, payload: dict[str, Any]) -> CapabilityReceipt:
        refs = _as_refs(payload.get("research_refs") or payload.get("research_ref") or payload.get("research_report_path"))
        invoked = bool(payload.get("research_used") or payload.get("should_research") or refs)
        gate_passed = bool(refs and _as_bool(payload.get("research_gate_passed", False)))
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


class LanceDBReceiptAdapter:
    name = "lancedb"

    def build(self, *, claim_verified: bool, payload: dict[str, Any]) -> CapabilityReceipt:
        hits = as_int(payload.get("lancedb_hits", payload.get("route_findings_hits", 0)))
        refs = _as_refs(payload.get("lancedb_refs") or payload.get("lancedb_ref"))
        invoked = bool(hits > 0 or refs or _pillar_present(payload, "lancedb"))
        gate_passed = bool(refs and _as_bool(payload.get("lancedb_gate_passed", False)))
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


class SemanticSearcherReceiptAdapter:
    name = "semantic_searcher"

    def build(self, *, claim_verified: bool, payload: dict[str, Any]) -> CapabilityReceipt:
        hits = as_int(payload.get("semantic_searcher_hits", payload.get("semantic_hits", 0)))
        refs = _as_refs(payload.get("semantic_searcher_refs") or payload.get("semantic_refs"))
        invoked = bool(hits > 0 or refs or payload.get("semantic_searcher_used"))
        gate_passed = bool(refs and _as_bool(payload.get("semantic_searcher_gate_passed", False)))
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


class UltraReviewReceiptAdapter:
    name = "ultra_review"

    def build(self, *, claim_verified: bool, payload: dict[str, Any]) -> CapabilityReceipt:
        invoked = bool(payload.get("invoked", False))
        report_path = str(payload.get("report_path") or "").strip()
        evidence_refs = [report_path] if report_path else []
        gate_passed = bool(payload.get("gate_passed", False) and evidence_refs)
        if not invoked and payload.get("reason"):
            failure_reason = str(payload.get("reason") or "")
        else:
            failure_reason = selected_failure_reason(
                selected=True,
                invoked=invoked,
                evidence_refs=evidence_refs,
                gate_passed=gate_passed,
            )
        return merge_capability_receipt(
            name=self.name,
            selected=True,
            invoked=invoked,
            evidence_refs=evidence_refs,
            gate_passed=gate_passed,
            outcome_contributed=bool(gate_passed and claim_verified and evidence_refs),
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


class SwarmQuietMomentReceiptAdapter:
    name = "swarm_quiet_moment"

    def build(self, *, claim_verified: bool, payload: dict[str, Any]) -> CapabilityReceipt:
        quiet = payload.get("quiet_moment") if isinstance(payload.get("quiet_moment"), dict) else {}
        if not quiet:
            report = payload.get("swarm_report") if isinstance(payload.get("swarm_report"), dict) else {}
            quiet = report.get("quiet_moment") if isinstance(report.get("quiet_moment"), dict) else {}
        invoked = bool(quiet)
        allowed = quiet.get("allowed_actions") if isinstance(quiet, dict) else []
        observe = quiet.get("observe") if isinstance(quiet.get("observe"), dict) else {}
        rollback = quiet.get("rollback") if isinstance(quiet.get("rollback"), dict) else {}
        non_mutating = bool(
            quiet.get("schema_version") == "nexus_quiet_moment.v1"
            and quiet.get("production_writes_allowed") is False
            and allowed == ["observe", "report", "rollback"]
            and observe.get("status")
            and rollback.get("status")
        )
        refs = []
        if invoked:
            refs.append("quiet_moment:nexus_quiet_moment.v1")
            if observe.get("status"):
                refs.append(f"observe:{observe.get('status')}")
            if rollback.get("status"):
                refs.append(f"rollback:{rollback.get('status')}")
        return merge_capability_receipt(
            name=self.name,
            selected=True,
            invoked=invoked,
            evidence_refs=refs,
            gate_passed=non_mutating,
            outcome_contributed=bool(non_mutating and claim_verified),
            executor_id=self.name,
            failure_reason=selected_failure_reason(
                selected=True,
                invoked=invoked,
                evidence_refs=refs,
                gate_passed=non_mutating,
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


class RepairLoopReceiptAdapter:
    name = "repair_loop"

    def build(self, *, claim_verified: bool, payload: dict[str, Any]) -> CapabilityReceipt:
        trace_path = str(payload.get("rlm_trace_path") or "").strip()
        refs = [trace_path] if trace_path else []
        invoked = bool(payload.get("rlm_trace_present") or trace_path)
        gate_passed = bool(invoked and claim_verified)
        return merge_capability_receipt(
            name=self.name,
            selected=True,
            invoked=invoked,
            evidence_refs=refs,
            gate_passed=gate_passed,
            outcome_contributed=bool(gate_passed and refs),
            executor_id="rlm_trace_bridge",
            failure_reason=selected_failure_reason(
                selected=True,
                invoked=invoked,
                evidence_refs=refs,
                gate_passed=gate_passed,
            ),
        )


RECEIPT_ADAPTERS: dict[str, CapabilityReceiptAdapter] = {
    adapter.name: adapter
    for adapter in (
        CodeIntelReceiptAdapter(),
        AutoreasonReceiptAdapter(),
        DDTreeReceiptAdapter(),
        HyperReceiptAdapter(),
        UltraReviewReceiptAdapter(),
        SwarmReceiptAdapter(),
        DroneReceiptAdapter(),
        NightshiftReceiptAdapter(),
        MemPalaceGateReceiptAdapter(),
        ArtifactGateReceiptAdapter(),
        ClaimGateReceiptAdapter(),
        DeliveryGateReceiptAdapter(),
        MemoryReceiptAdapter(),
        BeliefReceiptAdapter(),
        ResearchReceiptAdapter(),
        LanceDBReceiptAdapter(),
        SemanticSearcherReceiptAdapter(),
        SwarmQuietMomentReceiptAdapter(),
        RepairLoopReceiptAdapter(),
    )
}
