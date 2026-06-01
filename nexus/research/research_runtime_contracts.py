from __future__ import annotations

import re
from typing import Any


def build_research_doctor(
    *,
    research_preflight: dict[str, Any],
    research_session: dict[str, Any] | None = None,
    artifact_verified: bool = False,
) -> dict[str, Any]:
    """Lint research runtime packets before they are used as route evidence."""
    session = research_session if isinstance(research_session, dict) else {}
    stack = research_preflight.get("research_stack") if isinstance(research_preflight.get("research_stack"), dict) else {}
    checkpoints = [
        str(item.get("id") or "").strip()
        for item in (stack.get("checkpoints", []) or [])
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    ]
    required = {"fixed_budget_metric_contract", "packet_session_ledger", "claim_citation_verification", "candidate_tournament_receipt"}
    failures: list[str] = []
    if not research_preflight.get("present"):
        failures.append("preflight_missing")
    if required - set(checkpoints):
        failures.append("checkpoint_missing")
    if session and not session.get("logged"):
        failures.append("session_not_logged")
    if not artifact_verified:
        failures.append("artifact_not_verified")
    score = max(0.0, 1.0 - 0.25 * len(set(failures)))
    return {
        "schema": "nexus_research_doctor_v1",
        "status": "PASS" if score >= 0.9 else "FAIL",
        "score": round(score, 4),
        "failures": sorted(set(failures)),
        "metric_lint": {
            "primary_metric": "artifact_verified",
            "direction": "maximize",
            "decision": "keep" if artifact_verified and score >= 0.9 else "discard",
            "crash_policy": "fail_closed",
        },
        "checkpoints": sorted(set(checkpoints)),
    }


def build_claim_probe(
    *,
    task_desc: str,
    route: dict[str, Any],
    artifact_verified: bool = False,
) -> dict[str, Any]:
    """Create a lightweight pre-patch claim probe for API/SDK/contract uncertainty."""
    context = route.get("research_context", {}) if isinstance(route.get("research_context"), dict) else {}
    text = f"{task_desc} {' '.join(str(item) for item in context.get('blocked_assumptions', []) or [])}".lower()
    eligible = bool(
        context.get("blocked_assumptions")
        or "claim_uncertainty" in set(context.get("risk_flags", []) or [])
        or re.search(r"\b(api|sdk|contract|parameter|schema|claim|verify)\b", text)
    )
    refs = []
    if eligible:
        refs.append("probe:route_research_context")
        if artifact_verified:
            refs.append("probe:artifact_verified")
    return {
        "schema": "nexus_claim_probe_v1",
        "eligible": eligible,
        "invoked": eligible,
        "evidence_refs": refs,
        "gate_passed": bool(eligible and artifact_verified and refs),
        "decision": "allow_patch" if (not eligible or artifact_verified) else "block_patch",
        "reason": "claim_uncertainty_probe" if eligible else "not_claim_sensitive",
    }


def build_nexus_failure_analysis(
    *,
    artifact_verified: bool,
    tests_passed: bool,
    artifact_summary: dict[str, Any],
    research_doctor: dict[str, Any],
    claim_probe: dict[str, Any],
    gemini_invoked: bool,
    nexus_context_delivered: bool,
    self_heal_used: bool,
    result_report: dict[str, Any],
) -> dict[str, Any]:
    """Explain why a Nexus-wearing run did not become a verified delivery."""
    if artifact_verified:
        return {
            "schema": "nexus_failure_analysis_v1",
            "status": "PASS",
            "primary_cause": "verified_delivery",
            "nexus_gap": "",
            "owner": "none",
            "recoverable": False,
            "nexus_assisted": bool(gemini_invoked and nexus_context_delivered),
            "nexus_blocked_unsafe_delivery": False,
            "self_heal_status": "not_needed",
            "reasons": [],
            "next_action": "none",
        }

    reasons: list[str] = []
    changed = bool(artifact_summary.get("changed", False))
    mutation_required = bool(artifact_summary.get("mutation_required", False))
    model_patch_generated = bool(result_report.get("model_patch_generated", False))
    if not gemini_invoked:
        reasons.append("model_not_invoked")
    if not nexus_context_delivered:
        reasons.append("nexus_context_missing")
    if not tests_passed:
        reasons.append("tests_failed")
    if mutation_required and not changed:
        reasons.append("required_mutation_missing")
    if not model_patch_generated:
        reasons.append("model_patch_not_generated")
    if "artifact_not_verified" in set(research_doctor.get("failures", []) or []):
        reasons.append("research_doctor_artifact_not_verified")
    if str(claim_probe.get("decision") or "") == "block_patch":
        reasons.append("claim_probe_blocked_patch")

    if not gemini_invoked:
        primary = "model_not_invoked"
        owner = "nexus_invocation"
    elif mutation_required and not changed:
        primary = "flash_no_verified_mutation"
        owner = "nexus_retry_policy" if not self_heal_used else "model_output"
    elif not tests_passed:
        primary = "flash_patch_failed_tests"
        owner = "nexus_retry_policy" if not self_heal_used else "model_output"
    else:
        primary = "artifact_unverified"
        owner = "nexus_retry_policy" if not self_heal_used else "model_output"

    nexus_blocked = bool(
        str(claim_probe.get("decision") or "") == "block_patch"
        or str(research_doctor.get("status") or "").upper() == "FAIL"
    )
    self_heal_status = "used_but_unverified" if self_heal_used else "not_triggered"
    return {
        "schema": "nexus_failure_analysis_v1",
        "status": "ACTION_REQUIRED",
        "primary_cause": primary,
        "nexus_gap": "self_heal_failed" if self_heal_used else "bounded_self_heal_not_triggered",
        "owner": owner,
        "recoverable": bool(gemini_invoked),
        "nexus_assisted": bool(gemini_invoked and nexus_context_delivered),
        "nexus_blocked_unsafe_delivery": nexus_blocked,
        "self_heal_status": self_heal_status,
        "reasons": sorted(set(reasons)),
        "next_action": (
            "inspect_self_heal_failure_artifacts"
            if self_heal_used
            else "trigger_bounded_self_heal_before_accepting_flash_failure"
        ),
    }
