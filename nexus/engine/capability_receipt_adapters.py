from __future__ import annotations

import json
from pathlib import Path
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


def _explicit_bool(payload: dict[str, Any], key: str) -> bool:
    return key in payload and payload.get(key) is not None


def _fail_closed_ref(payload: dict[str, Any], key: str, ref: str) -> list[str]:
    if _explicit_bool(payload, key) and not _as_bool(payload.get(key)):
        return [ref]
    return []


def _pillar_present(payload: dict[str, Any], *names: str) -> bool:
    pillars = payload.get("pillars") if isinstance(payload.get("pillars"), dict) else {}
    for name in names:
        if _as_bool(pillars.get(name)):
            return True
    return False


class CodeIntelReceiptAdapter:
    name = "codeintel"

    def build(self, *, claim_verified: bool, payload: dict[str, Any]) -> CapabilityReceipt:
        refs = [
            payload.get("scan_report_path"),
            payload.get("impact_report_path"),
            payload.get("dci_locator_report_path"),
            *_as_refs(payload.get("dci_evidence_refs")),
        ]
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
            critique = payload.get("adversarial_critique") if isinstance(payload.get("adversarial_critique"), dict) else {}
            for candidate_id, item in sorted(critique.items()):
                if not isinstance(item, dict):
                    continue
                if item.get("fatal"):
                    refs.append(f"discriminator_fatal:{candidate_id}")
                critiques = item.get("critiques", []) if isinstance(item.get("critiques"), list) else []
                if critiques:
                    refs.append(f"discriminator_critiques:{candidate_id}:{len(critiques)}")
                defenses = item.get("defenses", []) if isinstance(item.get("defenses"), list) else []
                if defenses:
                    refs.append(f"discriminator_defenses:{candidate_id}:{len(defenses)}")
        clean_refs = [
            str(item).strip()
            for item in refs
            if item is not None and str(item).strip() and str(item).strip() != "None"
        ]
        winner_failed_discriminator = False
        critique = payload.get("adversarial_critique") if isinstance(payload.get("adversarial_critique"), dict) else {}
        if winner and isinstance(critique.get(str(winner)), dict):
            winner_failed_discriminator = bool(critique[str(winner)].get("fatal"))
        gate_passed = bool(winner and claim_verified and not winner_failed_discriminator)
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


class JudgePanelReceiptAdapter:
    name = "judge_panel"

    def build(self, *, claim_verified: bool, payload: dict[str, Any]) -> CapabilityReceipt:
        votes = payload.get("judge_panel_votes", []) or payload.get("llm_judge_panel_votes", []) or payload.get("panel_votes", []) or []
        winner = payload.get("judge_panel_winner") or payload.get("llm_judge_panel_winner") or payload.get("winner")
        report = str(payload.get("judge_panel_report_path") or payload.get("llm_judge_panel_report_path") or payload.get("judge_report") or "").strip()
        mode = str(payload.get("judge_panel_mode") or payload.get("llm_judge_panel_mode") or "").strip()
        invoked = bool(payload.get("judge_panel_used") or payload.get("llm_judge_panel_used") or votes or winner or report)
        refs = [report] if report else []
        if winner:
            refs.append(f"winner:{winner}")
        if votes:
            refs.append(f"panel_votes:{len(votes)}")
        if mode:
            refs.append(f"judge_mode:{mode}")
        gate_passed = bool(invoked and refs and _as_bool(payload.get("judge_panel_gate_passed", payload.get("llm_judge_panel_gate_passed", False))))
        return merge_capability_receipt(
            name=self.name,
            selected=True,
            invoked=invoked,
            evidence_refs=refs,
            gate_passed=gate_passed,
            outcome_contributed=bool(gate_passed and claim_verified),
            executor_id=self.name,
            failure_reason=selected_failure_reason(selected=True, invoked=invoked, evidence_refs=refs, gate_passed=gate_passed),
        )


class LlmJudgePanelReceiptAdapter(JudgePanelReceiptAdapter):
    name = "llm_judge_panel"


class ASIConstraintExtractorReceiptAdapter:
    name = "asi_constraint_extractor"

    def build(self, *, claim_verified: bool, payload: dict[str, Any]) -> CapabilityReceipt:
        constraints = payload.get("asi_constraints", []) or []
        blocked = payload.get("blocked_assumptions", []) or []
        lookup_refs = _as_refs(payload.get("asi_constraint_lookup_refs"))
        lookup_count = as_int(payload.get("asi_constraint_lookup_matched_count", 0))
        lookup_store = str(payload.get("asi_constraint_lookup_store_path") or "").strip()
        report = str(payload.get("asi_constraint_report_path") or "").strip()
        invoked = bool(report or constraints or blocked)
        refs = [report] if report else []
        if constraints:
            refs.append(f"extracted_constraints:{len(constraints)}")
        refs.extend(f"blocked:{item}" for item in blocked if str(item).strip())
        refs.extend(f"lookup:{item}" for item in lookup_refs)
        if lookup_count > 0:
            refs.append(f"lookup_matches:{lookup_count}")
        if lookup_store:
            refs.append(f"lookup_store:{lookup_store}")
        gate_passed = bool(invoked and refs and _as_bool(payload.get("asi_constraint_gate_passed", False)))
        return merge_capability_receipt(
            name=self.name,
            selected=True,
            invoked=invoked,
            evidence_refs=refs,
            gate_passed=gate_passed,
            outcome_contributed=bool(gate_passed and claim_verified),
            executor_id=self.name,
            failure_reason=selected_failure_reason(selected=True, invoked=invoked, evidence_refs=refs, gate_passed=gate_passed),
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
        refs = refs or _fail_closed_ref(payload, "mempalace_gate_passed", "mempalace:gate_failed")
        invoked = bool(_pillar_present(payload, "mempalace", "mempalace_gate") or refs or _explicit_bool(payload, "mempalace_gate_passed"))
        gate_passed = bool(refs and _as_bool(payload.get("mempalace_gate_passed", True)))
        return merge_capability_receipt(
            name=self.name,
            selected=True,
            invoked=invoked,
            evidence_refs=refs,
            gate_passed=gate_passed,
            outcome_contributed=bool(refs and (gate_passed or _explicit_bool(payload, "mempalace_gate_passed"))),
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
        refs = _as_refs(payload.get("artifact_refs") or payload.get("artifact_ref"))
        refs = refs or _fail_closed_ref(payload, "artifact_gate_passed", "artifact:gate_failed")
        invoked = bool(_pillar_present(payload, "artifact", "artifact_gate") or refs or _explicit_bool(payload, "artifact_gate_passed"))
        gate_passed = bool(refs and _as_bool(payload.get("artifact_gate_passed", True)))
        return merge_capability_receipt(
            name=self.name,
            selected=True,
            invoked=invoked,
            evidence_refs=refs,
            gate_passed=gate_passed,
            outcome_contributed=bool(refs and (gate_passed or _explicit_bool(payload, "artifact_gate_passed"))),
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
        refs = refs or _fail_closed_ref(payload, "claim_gate_invoked", "claim:gate_failed")
        invoked = bool(claim_verified or refs or _explicit_bool(payload, "claim_gate_invoked"))
        gate_passed = bool(refs and claim_verified)
        return merge_capability_receipt(
            name=self.name,
            selected=True,
            invoked=invoked,
            evidence_refs=refs,
            gate_passed=gate_passed,
            outcome_contributed=bool(refs and (gate_passed or _explicit_bool(payload, "claim_gate_invoked"))),
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
        refs = refs or _fail_closed_ref(payload, "delivery_gate_passed", "delivery:gate_failed")
        invoked = bool(payload.get("delivery_gate_passed") is not None or refs or payload.get("delivery_gate_invoked") or claim_verified)
        gate_passed = bool(refs and _as_bool(payload.get("delivery_gate_passed", claim_verified)))
        return merge_capability_receipt(
            name=self.name,
            selected=True,
            invoked=invoked,
            evidence_refs=refs,
            gate_passed=gate_passed,
            outcome_contributed=bool(refs and (gate_passed or _explicit_bool(payload, "delivery_gate_passed"))),
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
        semantic_refs = _as_refs(payload.get("semantic_searcher_refs") or payload.get("semantic_refs"))
        refs = list(dict.fromkeys([*refs, *semantic_refs]))
        invoked = bool(payload.get("belief_confidence") is not None or refs or _pillar_present(payload, "belief"))
        confidence_source = str(payload.get("belief_confidence_source") or payload.get("semantic_searcher_confidence_source") or "").strip()
        if confidence_source:
            refs.append(f"confidence_source:{confidence_source}")
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
        substantive_refs = [ref for ref in refs if not str(ref).endswith(":route_selected")]
        invoked = bool(payload.get("research_used") or payload.get("should_research") or refs)
        gate_passed = bool(substantive_refs and _as_bool(payload.get("research_gate_passed", False)))
        return CapabilityReceipt(
            name=self.name,
            selected=True,
            invoked=invoked,
            evidence_present=bool(substantive_refs),
            gate_passed=gate_passed,
            outcome_contributed=bool(gate_passed and claim_verified),
            executor_id=self.name,
            evidence_refs=tuple(refs),
            failure_reason=selected_failure_reason(
                selected=True,
                invoked=invoked,
                evidence_refs=substantive_refs,
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


class ArchitectureScoutReceiptAdapter:
    name = "architecture_scout"

    def build(self, *, claim_verified: bool, payload: dict[str, Any]) -> CapabilityReceipt:
        report = str(payload.get("architecture_scout_report_path") or "").strip()
        refs = [report] if report else []
        refs.extend(_as_refs(payload.get("architecture_refs")))
        refs.extend(f"blast_radius:{item}" for item in _as_refs(payload.get("blast_radius_refs")))
        invoked = bool(payload.get("architecture_scout_used") or refs)
        gate_passed = bool(invoked and refs and _as_bool(payload.get("architecture_scout_gate_passed", False)))
        return merge_capability_receipt(
            name=self.name,
            selected=True,
            invoked=invoked,
            evidence_refs=refs,
            gate_passed=gate_passed,
            outcome_contributed=bool(gate_passed and claim_verified),
            executor_id=self.name,
            failure_reason=selected_failure_reason(selected=True, invoked=invoked, evidence_refs=refs, gate_passed=gate_passed),
        )


class ExternalDocScoutReceiptAdapter:
    name = "external_doc_scout"

    def build(self, *, claim_verified: bool, payload: dict[str, Any]) -> CapabilityReceipt:
        refs = _as_refs(payload.get("external_doc_refs"))
        verified = _as_refs(payload.get("verified_claims"))
        rejected = _as_refs(payload.get("rejected_claims"))
        providers = _as_refs(payload.get("external_doc_scout_providers_used") or payload.get("providers_used"))
        cache_status = str(payload.get("external_doc_scout_cache_status") or payload.get("cache_status") or "").strip()
        verified_source_count = as_int(
            payload.get("external_doc_scout_verified_source_count", payload.get("verified_source_count", 0))
        )
        source_count = as_int(payload.get("external_doc_scout_source_count", payload.get("source_count", 0)))
        error_count = as_int(payload.get("external_doc_scout_error_count", payload.get("error_count", 0)))
        latency_ms = str(payload.get("external_doc_scout_latency_ms", payload.get("latency_ms", ""))).strip()
        cache_age_sec = str(payload.get("external_doc_scout_cache_age_sec", payload.get("cache_age_sec", ""))).strip()
        verified_external = bool(refs and verified_source_count > 0)
        if verified_external:
            refs.extend(f"verified_claim:{item}" for item in verified)
            refs.extend(f"rejected_claim:{item}" for item in rejected)
            refs.extend(f"provider:{item}" for item in providers)
        invoked = bool(payload.get("external_doc_scout_used") or verified_external)
        if invoked and (refs or verified_source_count > 0 or source_count > 0):
            if cache_status:
                refs.append(f"cache:{cache_status}")
            if verified_source_count > 0:
                refs.append(f"verified_sources:{verified_source_count}")
            if source_count > 0:
                refs.append(f"sources:{source_count}")
            refs.append(f"errors:{error_count}")
            if latency_ms:
                refs.append(f"latency_ms:{latency_ms}")
            if cache_age_sec:
                refs.append(f"cache_age_sec:{cache_age_sec}")
        gate_passed = bool(
            invoked
            and refs
            and verified_source_count > 0
            and _as_bool(payload.get("external_doc_scout_gate_passed", False))
        )
        return merge_capability_receipt(
            name=self.name,
            selected=True,
            invoked=invoked,
            evidence_refs=refs,
            gate_passed=gate_passed,
            outcome_contributed=bool(gate_passed and claim_verified),
            executor_id=self.name,
            failure_reason=selected_failure_reason(selected=True, invoked=invoked, evidence_refs=refs, gate_passed=gate_passed),
        )


class FormalReportReceiptAdapter:
    name = "formal_report"

    def build(self, *, claim_verified: bool, payload: dict[str, Any]) -> CapabilityReceipt:
        report = str(payload.get("formal_report_path") or "").strip()
        schema = str(payload.get("formal_report_schema_version") or "").strip()
        summary = str(payload.get("verification_summary_ref") or "").strip()
        refs = [item for item in (report, schema, summary) if item]
        invoked = bool(refs)
        gate_passed = bool(invoked and report and schema == "nexus_formal_report_v1" and _as_bool(payload.get("formal_report_gate_passed", False)))
        return merge_capability_receipt(
            name=self.name,
            selected=True,
            invoked=invoked,
            evidence_refs=refs,
            gate_passed=gate_passed,
            outcome_contributed=bool(gate_passed and claim_verified),
            executor_id=self.name,
            failure_reason=selected_failure_reason(selected=True, invoked=invoked, evidence_refs=refs, gate_passed=gate_passed),
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

    @staticmethod
    def _trace_readable(path: str) -> bool:
        target = Path(path)
        if not target.exists() or not target.is_file():
            return False
        try:
            first = next((line for line in target.read_text(encoding="utf-8").splitlines() if line.strip()), "")
            return bool(first and isinstance(json.loads(first), dict))
        except Exception:
            return False

    def build(self, *, claim_verified: bool, payload: dict[str, Any]) -> CapabilityReceipt:
        trace_path = str(payload.get("rlm_trace_path") or "").strip()
        refs = [trace_path] if trace_path else []
        attempt_id = str(payload.get("rlm_attempt_id") or "").strip()
        if attempt_id:
            refs.append(f"rlm_attempt:{attempt_id}")
        if trace_path and self._trace_readable(trace_path):
            refs.append("rlm_trace_status:readable_jsonl")
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


class GenericCapabilityReceiptAdapter:
    """Receipt adapter for capabilities whose runtime evidence follows the common *_used/*_refs pattern."""

    def __init__(
        self,
        name: str,
        *,
        executor_id: str | None = None,
        evidence_keys: tuple[str, ...] = (),
        used_keys: tuple[str, ...] = (),
        gate_key: str | None = None,
    ) -> None:
        self.name = name
        self.executor_id = executor_id or name
        self.evidence_keys = evidence_keys or (
            f"{name}_refs",
            f"{name}_ref",
            f"{name}_report_path",
            f"{name}_receipt_path",
        )
        self.used_keys = used_keys or (f"{name}_used", f"{name}_invoked")
        self.gate_key = gate_key or f"{name}_gate_passed"

    def build(self, *, claim_verified: bool, payload: dict[str, Any]) -> CapabilityReceipt:
        refs: list[str] = []
        for key in self.evidence_keys:
            refs.extend(_as_refs(payload.get(key)))
        refs = list(dict.fromkeys(refs))
        invoked = bool(refs or any(_as_bool(payload.get(key)) for key in self.used_keys))
        gate_passed = bool(refs and _as_bool(payload.get(self.gate_key, False)))
        return merge_capability_receipt(
            name=self.name,
            selected=True,
            invoked=invoked,
            evidence_refs=refs,
            gate_passed=gate_passed,
            outcome_contributed=bool(gate_passed and claim_verified),
            executor_id=self.executor_id,
            failure_reason=selected_failure_reason(
                selected=True,
                invoked=invoked,
                evidence_refs=refs,
                gate_passed=gate_passed,
            ),
        )


class HarnessPreflightSensorReceiptAdapter(GenericCapabilityReceiptAdapter):
    def __init__(self) -> None:
        super().__init__(
            "harness_preflight_sensor",
            evidence_keys=("harness_preflight_refs", "harness_preflight_report_path", "cost_lane"),
            used_keys=("harness_preflight_sensor_used",),
            gate_key="harness_preflight_sensor_gate_passed",
        )

    def build(self, *, claim_verified: bool, payload: dict[str, Any]) -> CapabilityReceipt:
        refs = _as_refs(payload.get("harness_preflight_refs"))
        refs.extend(_as_refs(payload.get("harness_preflight_report_path")))
        cost_lane = str(payload.get("cost_lane") or "").strip()
        if cost_lane:
            refs.append(f"cost_lane:{cost_lane}")
        refs = list(dict.fromkeys(refs))
        invoked = bool(refs or _as_bool(payload.get("harness_preflight_sensor_used")))
        gate_passed = bool(
            invoked
            and refs
            and _as_bool(payload.get("harness_preflight_sensor_gate_passed"))
            and _as_bool(payload.get("capability_wired"))
            and _as_bool(payload.get("executor_ready"))
            and cost_lane in {"lite", "standard", "hardened"}
        )
        return merge_capability_receipt(
            name=self.name,
            selected=True,
            invoked=invoked,
            evidence_refs=refs,
            gate_passed=gate_passed,
            outcome_contributed=bool(gate_passed and claim_verified),
            executor_id=self.name,
            failure_reason=selected_failure_reason(selected=True, invoked=invoked, evidence_refs=refs, gate_passed=gate_passed),
        )


class SemanticFailureSensorReceiptAdapter(GenericCapabilityReceiptAdapter):
    def __init__(self) -> None:
        super().__init__(
            "semantic_failure_sensor",
            evidence_keys=("semantic_failure_refs", "failure_cause", "likely_fix"),
            used_keys=("semantic_failure_sensor_used",),
            gate_key="semantic_failure_sensor_gate_passed",
        )

    def build(self, *, claim_verified: bool, payload: dict[str, Any]) -> CapabilityReceipt:
        refs = _as_refs(payload.get("semantic_failure_refs"))
        for key in ("failure_cause", "likely_fix"):
            value = str(payload.get(key) or "").strip()
            if value:
                refs.append(f"{key}:{value}")
        retry_policy = payload.get("retry_policy") if isinstance(payload.get("retry_policy"), dict) else {}
        if retry_policy:
            refs.append(f"retry_policy:max={retry_policy.get('max_retries')}")
        refs = list(dict.fromkeys(refs))
        invoked = bool(refs or _as_bool(payload.get("semantic_failure_sensor_used")))
        gate_passed = bool(
            invoked
            and refs
            and _as_bool(payload.get("semantic_failure_sensor_gate_passed"))
            and retry_policy.get("requires_evidence_delta") is True
            and retry_policy.get("allow_blind_retry") is False
        )
        return merge_capability_receipt(
            name=self.name,
            selected=True,
            invoked=invoked,
            evidence_refs=refs,
            gate_passed=gate_passed,
            outcome_contributed=bool(gate_passed and claim_verified),
            executor_id=self.name,
            failure_reason=selected_failure_reason(selected=True, invoked=invoked, evidence_refs=refs, gate_passed=gate_passed),
        )


class BddAcceptanceSkillReceiptAdapter(GenericCapabilityReceiptAdapter):
    def __init__(self) -> None:
        super().__init__(
            "bdd_acceptance_skill",
            evidence_keys=("bdd_acceptance_refs", "bdd_acceptance_report_path"),
            used_keys=("bdd_acceptance_skill_used",),
            gate_key="bdd_acceptance_skill_gate_passed",
        )

    def build(self, *, claim_verified: bool, payload: dict[str, Any]) -> CapabilityReceipt:
        refs = _as_refs(payload.get("bdd_acceptance_refs"))
        refs.extend(_as_refs(payload.get("bdd_acceptance_report_path")))
        refs = list(dict.fromkeys(refs))
        invoked = bool(refs or _as_bool(payload.get("bdd_acceptance_skill_used")))
        business_verified = _as_bool(payload.get("business_verified"))
        gate_passed = bool(
            invoked
            and refs
            and claim_verified
            and business_verified
            and _as_bool(payload.get("bdd_acceptance_skill_gate_passed"))
        )
        return merge_capability_receipt(
            name=self.name,
            selected=True,
            invoked=invoked,
            evidence_refs=refs,
            gate_passed=gate_passed,
            outcome_contributed=bool(gate_passed),
            executor_id=self.name,
            failure_reason=selected_failure_reason(selected=True, invoked=invoked, evidence_refs=refs, gate_passed=gate_passed),
        )


class MsaRouterReceiptAdapter(GenericCapabilityReceiptAdapter):
    def __init__(self) -> None:
        super().__init__(
            "msa_router",
            evidence_keys=("msa_router_refs", "msa_rerank_reasons", "msa_router_report_path"),
            used_keys=("msa_router_used", "msa_routing_used"),
            gate_key="msa_router_gate_passed",
        )

    def build(self, *, claim_verified: bool, payload: dict[str, Any]) -> CapabilityReceipt:
        refs = _as_refs(payload.get("msa_router_refs"))
        refs.extend(f"rerank:{item}" for item in _as_refs(payload.get("msa_rerank_reasons")))
        if payload.get("msa_router_report_path"):
            refs.append(str(payload.get("msa_router_report_path")))
        candidate_count = as_int(payload.get("msa_candidate_count", 0))
        top_score = str(payload.get("msa_top_score", "")).strip()
        if candidate_count > 0:
            refs.append(f"candidate_count:{candidate_count}")
        if top_score:
            refs.append(f"top_score:{top_score}")
        refs = list(dict.fromkeys(refs))
        invoked = bool(refs or payload.get("msa_router_used") or payload.get("msa_routing_used"))
        gate_passed = bool(refs and _as_bool(payload.get("msa_router_gate_passed", False)))
        return merge_capability_receipt(
            name=self.name,
            selected=True,
            invoked=invoked,
            evidence_refs=refs,
            gate_passed=gate_passed,
            outcome_contributed=bool(gate_passed and claim_verified),
            executor_id=self.executor_id,
            failure_reason=selected_failure_reason(
                selected=True,
                invoked=invoked,
                evidence_refs=refs,
                gate_passed=gate_passed,
            ),
        )


class JitValidationReceiptAdapter(GenericCapabilityReceiptAdapter):
    def __init__(self) -> None:
        super().__init__(
            "jit_validation",
            evidence_keys=("jit_refs", "jit_report_path", "verify_command_refs", "replay_refs"),
            used_keys=("jit_used", "jit_validation_used", "verify_commands_executed"),
            gate_key="jit_gate_passed",
        )


RECEIPT_ADAPTERS: dict[str, CapabilityReceiptAdapter] = {
    adapter.name: adapter
    for adapter in (
        CodeIntelReceiptAdapter(),
        AutoreasonReceiptAdapter(),
        JudgePanelReceiptAdapter(),
        LlmJudgePanelReceiptAdapter(),
        ASIConstraintExtractorReceiptAdapter(),
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
        ArchitectureScoutReceiptAdapter(),
        ExternalDocScoutReceiptAdapter(),
        FormalReportReceiptAdapter(),
        SwarmQuietMomentReceiptAdapter(),
        RepairLoopReceiptAdapter(),
        MsaRouterReceiptAdapter(),
        JitValidationReceiptAdapter(),
        GenericCapabilityReceiptAdapter("acceptance_check", evidence_keys=("acceptance_refs", "acceptance_report", "acceptance_report_path")),
        GenericCapabilityReceiptAdapter("autonomic_router", evidence_keys=("autonomic_route_refs", "autonomic_route", "policy_reason")),
        GenericCapabilityReceiptAdapter("benchmark", evidence_keys=("benchmark_refs", "benchmark_report", "benchmark_report_path", "public_claim_gate_ref")),
        GenericCapabilityReceiptAdapter("direct_mode", evidence_keys=("direct_mode_refs", "run_report", "completion_envelope", "verify_commands")),
        GenericCapabilityReceiptAdapter("federation", evidence_keys=("federation_refs", "federation_report_path")),
        GenericCapabilityReceiptAdapter("file_lock", evidence_keys=("file_lock_refs", "locked_files", "conflicts", "denied_paths")),
        GenericCapabilityReceiptAdapter("forecast_gate", evidence_keys=("forecast_refs", "risk_forecast", "forecast_report_path")),
        GenericCapabilityReceiptAdapter("integration_manager", evidence_keys=("integration_refs", "merge_result", "evidence_chain")),
        BddAcceptanceSkillReceiptAdapter(),
        HarnessPreflightSensorReceiptAdapter(),
        GenericCapabilityReceiptAdapter("learn_mode", evidence_keys=("learn_refs", "claims_count_ref", "verified_claims_ref", "citations")),
        GenericCapabilityReceiptAdapter("learn_phase_slo", evidence_keys=("learn_phase_slo_refs", "phase_slo_report_path", "policy_reasoning")),
        GenericCapabilityReceiptAdapter("learn_scheduler", evidence_keys=("learn_scheduler_refs", "refresh_report_path", "alert_paths")),
        GenericCapabilityReceiptAdapter("meta_opt", evidence_keys=("meta_opt_refs", "tuning_delta", "rule_lifecycle_decision")),
        GenericCapabilityReceiptAdapter("metabolism", evidence_keys=("metabolism_refs", "checkpoint", "resume_available")),
        GenericCapabilityReceiptAdapter("multi_agent", evidence_keys=("multi_agent_refs", "worktree", "gate_status", "allowed_files")),
        GenericCapabilityReceiptAdapter("oracle_shadow", evidence_keys=("oracle_shadow_refs", "shadow_tid", "promotion_status", "report_path")),
        GenericCapabilityReceiptAdapter("plan_quality_gate", evidence_keys=("plan_quality_refs", "plan_quality_verdict", "plan_quality_report_path")),
        GenericCapabilityReceiptAdapter("pregate", evidence_keys=("pregate_refs", "pregate_verdict", "blocked_reason", "cli_pregate_results")),
        GenericCapabilityReceiptAdapter("registry_sync", evidence_keys=("registry_sync_refs", "skills_count", "sync_delta")),
        GenericCapabilityReceiptAdapter("research_control_plane", evidence_keys=("research_control_refs", "elimination_matrix", "rollback_trace", "semantic_status")),
        GenericCapabilityReceiptAdapter("research_route", evidence_keys=("research_route_refs", "recommended_flow", "route_features", "explain_payload")),
        GenericCapabilityReceiptAdapter("sandbox", evidence_keys=("sandbox_refs", "sandbox_path", "replay_artifact")),
        SemanticFailureSensorReceiptAdapter(),
        GenericCapabilityReceiptAdapter("stress_test", evidence_keys=("stress_test_refs", "stress_test_report", "stress_test_report_path")),
        GenericCapabilityReceiptAdapter("ui_validator", evidence_keys=("ui_validator_refs", "ui_validation_report", "ui_validation_report_path")),
        GenericCapabilityReceiptAdapter("xray", evidence_keys=("xray_refs", "xray_findings", "xray_report_path")),
    )
}
