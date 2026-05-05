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
