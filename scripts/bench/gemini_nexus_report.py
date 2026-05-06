#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

from nexus.engine.capability_aliases import normalize_capability_name
from nexus.engine.capability_receipt_policy import (
    is_public_claim_capability,
    is_route_quality_actionable_receipt,
    public_gate_ignored_reasons,
    public_safe_receipt_names,
    route_quality_ignored_reasons,
)
from scripts.bench.ab_eval import compare_datasets, load_runs


_ROUTE_QUALITY_GATE_THRESHOLDS = {
    "selected_to_invoked_rate": 0.70,
    "invoked_to_evidence_rate": 0.95,
    "evidence_to_outcome_rate": 0.90,
    "unnecessary_selected_rate_max": 0.30,
}


def _pct(value: Any) -> str:
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return "n/a"


def _num(value: Any, digits: int = 2) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "n/a"


def _wall_speedup(delta_sec: float, baseline_sec: float) -> str:
    if baseline_sec <= 0:
        return "n/a"
    return _pct(-delta_sec / baseline_sec)


def _token_status_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        status = str(row.get("token_capture_status") or "unknown").strip().lower() or "unknown"
        counts[status] = counts.get(status, 0) + 1
    return counts


def _count_text(counts: dict[str, int], key: str) -> str:
    return str(counts.get(key, 0))


def _scope_summary(rows: list[dict[str, Any]]) -> dict[str, int]:
    task_ids = {str(row.get("task_id") or "") for row in rows if row.get("task_id")}
    trials = {
        int(row.get("trial_index") or 1)
        for row in rows
        if str(row.get("trial_index") or "").strip()
    }
    return {
        "rows": len(rows),
        "unique_tasks": len(task_ids),
        "repeat_trials": max(trials) if trials else 1,
    }


def _infra_invalid_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        if bool(row.get("run_eligible", True)):
            continue
        reason = str(row.get("infra_invalid_reason") or "unknown").strip() or "unknown"
        counts[reason] = counts.get(reason, 0) + 1
    return counts


def _run_eligible_count(rows: list[dict[str, Any]]) -> int:
    return sum(1 for row in rows if bool(row.get("run_eligible", True)))


def _is_verified(row: dict[str, Any]) -> bool:
    return str(row.get("semantic_status", "")).strip().upper() == "VERIFIED"


def _eligible_solve_rate(rows: list[dict[str, Any]]) -> float:
    eligible = [row for row in rows if bool(row.get("run_eligible", True))]
    if not eligible:
        return 0.0
    return sum(1 for row in eligible if _is_verified(row)) / len(eligible)


def _reasons_text(counts: dict[str, int]) -> str:
    if not counts:
        return "none"
    return ", ".join(f"{reason}:{count}" for reason, count in sorted(counts.items()))


def _capability_coverage_rows(report: dict[str, Any]) -> list[str]:
    coverage = ((report.get("capability_coverage") or {}).get("b") or {})
    if not isinstance(coverage, dict) or not coverage:
        return ["| none | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | NO | none | none |"]
    rows: list[str] = []
    for name in sorted(coverage):
        item = coverage.get(name) or {}
        failure_reasons = item.get("failure_reasons", {})
        failure_text = _reasons_text(failure_reasons if isinstance(failure_reasons, dict) else {})
        rows.append(
            "| "
            + " | ".join(
                [
                    str(name),
                    _pct(item.get("selected_rate")),
                    _pct(item.get("invoked_rate")),
                    _pct(item.get("evidence_rate")),
                    _pct(item.get("gate_rate")),
                    _pct(item.get("outcome_rate")),
                    "YES" if item.get("public_safe") else "NO",
                    str(item.get("source") or "legacy"),
                    failure_text,
                ]
            )
            + " |"
        )
    return rows


def _ratio_text(item: dict[str, Any], key: str, total: int) -> str:
    count = int(item.get(f"{key}_count", 0) or 0)
    return f"{count}/{total}"


def _safe_ratio(num: float, den: float) -> float:
    if den <= 0:
        return 0.0
    return num / den


def _route_quality_ignored_reasons(name: str) -> set[str]:
    return route_quality_ignored_reasons(name)


def _coverage_route_quality_actionable(name: str, item: dict[str, Any]) -> bool:
    if bool(item.get("public_safe")):
        return True
    if any(float(item.get(f"{key}_count", 0) or 0) > 0 for key in ("invoked", "evidence", "gate", "outcome")):
        return True
    canonical_name = normalize_capability_name(name)
    if not is_public_claim_capability(canonical_name):
        return False
    if float(item.get("selected_count", 0) or 0) <= 0:
        return False
    failure_reasons = item.get("failure_reasons", {})
    reasons = {str(reason) for reason in failure_reasons if str(reason).strip()} if isinstance(failure_reasons, dict) else set()
    return not (reasons and reasons <= _route_quality_ignored_reasons(canonical_name))


def _route_quality_metrics(report: dict[str, Any], arm: str) -> dict[str, float]:
    coverage = ((report.get("capability_coverage") or {}).get(arm) or {})
    if not isinstance(coverage, dict) or not coverage:
        return {
            "selected_to_invoked_rate": 0.0,
            "invoked_to_evidence_rate": 0.0,
            "evidence_to_outcome_rate": 0.0,
            "unnecessary_selected_rate": 0.0,
        }
    selected = 0.0
    invoked = 0.0
    evidence = 0.0
    outcome = 0.0
    for name, item in coverage.items():
        if not isinstance(item, dict):
            continue
        if not _coverage_route_quality_actionable(str(name), item):
            continue
        selected += float(item.get("selected_count", 0) or 0)
        invoked += float(item.get("invoked_count", 0) or 0)
        evidence += float(item.get("evidence_count", 0) or 0)
        outcome += float(item.get("outcome_count", 0) or 0)
    selected_to_invoked = _safe_ratio(invoked, selected)
    invoked_to_evidence = _safe_ratio(evidence, invoked)
    evidence_to_outcome = _safe_ratio(outcome, evidence)
    unnecessary_selected = _safe_ratio(max(selected - invoked, 0.0), selected)
    return {
        "selected_to_invoked_rate": selected_to_invoked,
        "invoked_to_evidence_rate": invoked_to_evidence,
        "evidence_to_outcome_rate": evidence_to_outcome,
        "unnecessary_selected_rate": unnecessary_selected,
    }


def _route_tactical_metrics(rows: list[dict[str, Any]]) -> dict[str, float]:
    eligible = [row for row in rows if bool(row.get("run_eligible", True))]
    traced = [
        row
        for row in eligible
        if str(row.get("openseeker_schema_version") or "").strip()
        and (
            int(row.get("route_tactical_tool_count", 0) or 0) > 0
            or int(row.get("route_evidence_required_count", 0) or 0) > 0
        )
    ]

    def _mean(key: str) -> float:
        if not traced:
            return 0.0
        return sum(float(row.get(key, 0.0) or 0.0) for row in traced) / len(traced)

    return {
        "trace_present_rate": len(traced) / len(eligible) if eligible else 0.0,
        "avg_route_tactical_tool_count": _mean("route_tactical_tool_count"),
        "avg_route_evidence_required_count": _mean("route_evidence_required_count"),
    }


def _jsonish(value: Any, fallback: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return fallback
    return value if value is not None else fallback


def _research_receipts(row: dict[str, Any]) -> list[dict[str, Any]]:
    receipts = _jsonish(row.get("capability_receipts"), [])
    if not isinstance(receipts, list):
        return []
    return [
        item
        for item in receipts
        if isinstance(item, dict) and str(item.get("name") or item.get("capability") or "") == "research"
    ]


def _receipt_route_quality_actionable(receipt: dict[str, Any]) -> bool:
    return is_route_quality_actionable_receipt(receipt)


def _route_tactical_tool_map(row: dict[str, Any]) -> list[dict[str, Any]]:
    payload = _jsonish(row.get("route_tactical_tool_map"), [])
    if not isinstance(payload, list) or not payload:
        payload = _jsonish(row.get("route_tactical_tool_map_json"), [])
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def _row_route_quality_counts(row: dict[str, Any]) -> dict[str, int] | None:
    receipts = _jsonish(row.get("capability_receipts"), [])
    tactical_map = _route_tactical_tool_map(row)
    evidence_required_tools = {
        normalize_capability_name(item.get("capability") or item.get("name"))
        for item in tactical_map
        if bool(item.get("evidence_required"))
    }
    evidence_required_tools = {name for name in evidence_required_tools if name}
    if (not isinstance(receipts, list) or not receipts) and not evidence_required_tools:
        return None
    receipts = receipts if isinstance(receipts, list) else []
    selected = invoked = evidence = outcome = 0
    counted_names: set[str] = set()
    receipts_by_name: dict[str, list[dict[str, Any]]] = {}
    for receipt in receipts:
        if not isinstance(receipt, dict):
            continue
        name = normalize_capability_name(receipt.get("name") or receipt.get("capability"))
        if name:
            receipts_by_name.setdefault(name, []).append(receipt)
        if not _receipt_route_quality_actionable(receipt):
            continue
        if name:
            counted_names.add(name)
        if bool(receipt.get("selected", False)):
            selected += 1
        if bool(receipt.get("invoked", False)):
            invoked += 1
        if bool(receipt.get("evidence_present") or receipt.get("evidence")):
            evidence += 1
        if bool(receipt.get("outcome_contributed", False)):
            outcome += 1
    for name in sorted(evidence_required_tools - counted_names):
        selected += 1
        matching_receipts = receipts_by_name.get(name, [])
        if any(bool(receipt.get("invoked", False)) for receipt in matching_receipts):
            invoked += 1
        if any(bool(receipt.get("evidence_present") or receipt.get("evidence")) for receipt in matching_receipts):
            evidence += 1
        if any(bool(receipt.get("outcome_contributed", False)) for receipt in matching_receipts):
            outcome += 1
    return {
        "selected": selected,
        "invoked": invoked,
        "evidence": evidence,
        "outcome": outcome,
    }


def _research_preflight_metrics(rows: list[dict[str, Any]]) -> dict[str, float]:
    total = len(rows)
    if total <= 0:
        return {
            "preflight_present_rate": 0.0,
            "preflight_blocked_rate": 0.0,
            "claim_uncertainty_caught_rate": 0.0,
            "research_evidence_present_rate": 0.0,
            "research_gate_passed_rate": 0.0,
            "session_ledger_logged_rate": 0.0,
            "research_doctor_pass_rate": 0.0,
            "avg_research_doctor_score": 0.0,
            "claim_probe_eligible_rate": 0.0,
            "claim_probe_gate_pass_rate": 0.0,
            "autoreason_ab_factory_ready_rate": 0.0,
            "autoreason_ab_winner_rate": 0.0,
            "governance_event_present_rate": 0.0,
            "governance_event_avg_count": 0.0,
            "evidence_accepted_event_rate": 0.0,
            "learning_decision_event_rate": 0.0,
            "audit_failed_event_rate": 0.0,
        }
    present = 0
    blocked = 0
    claim_uncertainty = 0
    evidence_present = 0
    gate_passed = 0
    session_logged = 0
    doctor_pass = 0
    doctor_score_total = 0.0
    claim_probe_eligible = 0
    claim_probe_gate = 0
    ab_factory_ready = 0
    ab_winner = 0
    governance_event_present = 0
    governance_event_count = 0
    evidence_accepted_event = 0
    learning_decision_event = 0
    audit_failed_event = 0
    for row in rows:
        preflight = _jsonish(row.get("research_preflight"), {})
        preflight = preflight if isinstance(preflight, dict) else {}
        route = preflight.get("route") if isinstance(preflight.get("route"), dict) else {}
        context = route.get("research_context") if isinstance(route.get("research_context"), dict) else {}
        risk_flags = set(context.get("risk_flags", []) or [])
        blocked_assumptions = set(context.get("blocked_assumptions", []) or [])
        receipts = _research_receipts(row)
        if preflight or bool(row.get("research_preflight_present")) or bool(row.get("research_used")):
            present += 1
        if bool(preflight.get("blocked")) or bool(row.get("research_preflight_blocked")):
            blocked += 1
        if "claim_uncertainty" in risk_flags or "api_contract_not_verified" in blocked_assumptions or bool(row.get("claim_uncertainty")):
            claim_uncertainty += 1
        if bool(row.get("research_evidence_present")) or any(bool(item.get("evidence_present") or item.get("evidence")) for item in receipts):
            evidence_present += 1
        if bool(row.get("research_gate_passed")) or any(bool(item.get("gate_passed") or item.get("gate")) for item in receipts):
            gate_passed += 1
        session = _jsonish(row.get("research_session"), {})
        if (isinstance(session, dict) and bool(session.get("logged"))) or bool(row.get("research_session_logged")):
            session_logged += 1
        doctor = _jsonish(row.get("research_doctor"), {})
        doctor = doctor if isinstance(doctor, dict) else {}
        if str(row.get("research_doctor_status") or doctor.get("status") or "").upper() == "PASS":
            doctor_pass += 1
        doctor_score_total += float(row.get("research_doctor_score") or doctor.get("score") or 0.0)
        probe = _jsonish(row.get("claim_probe"), {})
        probe = probe if isinstance(probe, dict) else {}
        if bool(row.get("claim_probe_eligible") or probe.get("eligible")):
            claim_probe_eligible += 1
            if bool(row.get("claim_probe_gate_passed") or probe.get("gate_passed")):
                claim_probe_gate += 1
        if str(row.get("autoreason_candidate_factory_status") or "").upper() == "READY":
            ab_factory_ready += 1
        if str(row.get("autoreason_winner_role") or row.get("autoreason_winner") or "") == "AB":
            ab_winner += 1
        governance_events = _jsonish(row.get("governance_events"), [])
        governance_events = governance_events if isinstance(governance_events, list) else []
        governance_types = {
            str(item.get("event_type") or "")
            for item in governance_events
            if isinstance(item, dict) and str(item.get("event_type") or "")
        }
        if not governance_types:
            row_types = _jsonish(row.get("governance_event_types"), [])
            if isinstance(row_types, list):
                governance_types = {str(item) for item in row_types if str(item)}
        count = int(row.get("governance_event_count") or len(governance_events) or len(governance_types))
        governance_event_count += count
        if count > 0 or governance_types:
            governance_event_present += 1
        if "evidence_accepted" in governance_types:
            evidence_accepted_event += 1
        if "learning_decision" in governance_types:
            learning_decision_event += 1
        if "audit_failed" in governance_types:
            audit_failed_event += 1
    return {
        "preflight_present_rate": present / total,
        "preflight_blocked_rate": blocked / total,
        "claim_uncertainty_caught_rate": claim_uncertainty / total,
        "research_evidence_present_rate": evidence_present / total,
        "research_gate_passed_rate": gate_passed / total,
        "session_ledger_logged_rate": session_logged / total,
        "research_doctor_pass_rate": doctor_pass / total,
        "avg_research_doctor_score": doctor_score_total / total,
        "claim_probe_eligible_rate": claim_probe_eligible / total,
        "claim_probe_gate_pass_rate": (claim_probe_gate / claim_probe_eligible) if claim_probe_eligible else 1.0,
        "autoreason_ab_factory_ready_rate": ab_factory_ready / total,
        "autoreason_ab_winner_rate": ab_winner / total,
        "governance_event_present_rate": governance_event_present / total,
        "governance_event_avg_count": governance_event_count / total,
        "evidence_accepted_event_rate": evidence_accepted_event / total,
        "learning_decision_event_rate": learning_decision_event / total,
        "audit_failed_event_rate": audit_failed_event / total,
    }


def _brain_hub_guidance_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    if total <= 0:
        return {
            "present_rate": 0.0,
            "audit_passed_rate": 0.0,
            "document_avg_count": 0.0,
            "phases": [],
            "failure_count": 0,
        }
    present = 0
    audit_passed = 0
    document_count = 0
    failure_count = 0
    phases: set[str] = set()
    for row in rows:
        payload = _jsonish(row.get("brain_hub_guidance"), {})
        payload = payload if isinstance(payload, dict) else {}
        guidance = payload.get("guidance") if isinstance(payload.get("guidance"), dict) else {}
        if bool(row.get("brain_hub_guidance_present")) or guidance:
            present += 1
        if bool(row.get("brain_hub_guidance_audit_passed")) or bool(payload.get("audit_passed")):
            audit_passed += 1
        document_count += int(payload.get("document_count", 0) or 0)
        failures = payload.get("failures", [])
        if isinstance(failures, list):
            failure_count += len(failures)
        row_phases = row.get("brain_hub_guidance_phases")
        if isinstance(row_phases, list):
            phases.update(str(item) for item in row_phases if str(item))
        phases.update(str(item) for item in guidance.keys() if str(item))
    return {
        "present_rate": present / total,
        "audit_passed_rate": audit_passed / total,
        "document_avg_count": document_count / total,
        "phases": sorted(phases),
        "failure_count": failure_count,
    }


def _activation_status(item: dict[str, Any]) -> str:
    selected = int(item.get("selected_count", 0) or 0)
    invoked = int(item.get("invoked_count", 0) or 0)
    evidence = int(item.get("evidence_count", 0) or 0)
    gate = int(item.get("gate_count", 0) or 0)
    outcome = int(item.get("outcome_count", 0) or 0)
    if selected <= 0:
        if invoked > 0 or evidence > 0 or gate > 0 or outcome > 0:
            return "observed_unplanned"
        return "not_selected"
    if item.get("public_safe"):
        return "public_safe"
    if invoked > 0 or evidence > 0 or gate > 0:
        return "observed_partial"
    return "selected_only"


def _activation_note(status: str) -> str:
    if status == "public_safe":
        return "Can claim: selected, invoked, evidenced, and gated."
    if status == "observed_partial":
        return "Observed, but not enough evidence for a public capability claim."
    if status == "selected_only":
        return "Selected but not fully invoked/evidenced/gated."
    if status == "observed_unplanned":
        return "Evidence exists, but route selection did not record this capability."
    return "Not selected in this run."


def _capability_activation_visible(name: str, item: dict[str, Any]) -> bool:
    if is_public_claim_capability(name):
        return True
    if str(name) in {"artifact_gate", "claim_gate", "delivery_gate", "mempalace_gate"} and bool(item.get("selected_count", 0)):
        return True
    if bool(item.get("public_safe")):
        return True
    return any(float(item.get(f"{key}_count", 0) or 0) > 0 for key in ("invoked", "evidence", "gate", "outcome"))


def _capability_activation_rows(report: dict[str, Any]) -> list[str]:
    coverage = ((report.get("capability_coverage") or {}).get("b") or {})
    total = int(((report.get("b") or {}).get("summary") or {}).get("total_runs", 0) or 0)
    if not isinstance(coverage, dict) or not coverage:
        return ["| none | not_selected | 0/0 | 0/0 | 0/0 | 0/0 | 0/0 | none | Not selected in this run. |"]
    rows: list[str] = []
    for name in sorted(coverage):
        item = coverage.get(name) or {}
        if not _capability_activation_visible(str(name), item):
            continue
        status = _activation_status(item)
        rows.append(
            "| "
            + " | ".join(
                [
                    str(name),
                    status,
                    _ratio_text(item, "selected", total),
                    _ratio_text(item, "invoked", total),
                    _ratio_text(item, "evidence", total),
                    _ratio_text(item, "gate", total),
                    _ratio_text(item, "outcome", total),
                    str(item.get("source") or "legacy"),
                    _activation_note(status),
                ]
            )
            + " |"
        )
    return rows or ["| none | not_selected | 0/0 | 0/0 | 0/0 | 0/0 | 0/0 | none | Not selected in this run. |"]


def _per_capability_public_gate(report: dict[str, Any]) -> dict[str, Any]:
    coverage = ((report.get("capability_coverage") or {}).get("b") or {})
    failures: list[str] = []
    public_safe: list[str] = []
    if not isinstance(coverage, dict):
        return {"verdict": "FAIL", "public_safe": [], "failures": ["coverage_missing"]}
    for name, item in sorted(coverage.items()):
        if not isinstance(item, dict):
            failures.append(f"{name}:invalid_coverage")
            continue
        canonical_name = normalize_capability_name(name)
        if not is_public_claim_capability(canonical_name):
            continue
        selected = float(item.get("selected_rate", 0.0) or 0.0)
        if selected <= 0:
            continue
        if item.get("source") != "capability_receipts":
            failures.append(f"{name}:receipt_source_missing")
            continue
        if item.get("public_safe"):
            public_safe.append(canonical_name)
        else:
            failure_reasons = item.get("failure_reasons", {})
            if isinstance(failure_reasons, dict):
                reasons = {str(reason) for reason in failure_reasons if str(reason).strip()}
                ignored = public_gate_ignored_reasons(name)
                if reasons and reasons <= ignored:
                    continue
            missing = [
                layer
                for layer in ("invoked", "evidence", "gate")
                if float(item.get(f"{layer}_rate", 0.0) or 0.0) < selected
            ]
            failures.append(f"{name}:{'+'.join(missing) or 'not_public_safe'}")
    return {
        "verdict": "PASS" if not failures else "FAIL",
        "public_safe": public_safe,
        "failures": failures,
    }


def _claim_gate_breakdown(
    *,
    public_gate: dict[str, Any],
    capability_gate: dict[str, Any],
    token_public_safe: str,
) -> dict[str, dict[str, Any]]:
    failures = set(public_gate.get("failures", []) or [])
    performance_failures = sorted(
        reason
        for reason in failures
        if reason in {"parallel_smoke", "missing_rows", "task_trial_mismatch", "metric_parse_error"}
    )
    wearing_failures = sorted(
        reason
        for reason in failures
        if reason
        in {
            "nexus_wearing_below_threshold",
            "model_uses_nexus_below_threshold",
            "gemini_uses_nexus_below_threshold",
            "nexus_usage_valid_below_threshold",
            "phase_completion_below_threshold",
            "claim_verified_below_threshold",
            "rlm_submit_without_a_gate",
            "rlm_success_without_verified_trace",
            "rlm_trace_quality_below_threshold",
            "rlm_x_loop_budget_missing",
        }
    )
    cost_failures = sorted(
        reason
        for reason in failures
        if reason in {"without_token_measured_below_threshold", "with_token_measured_below_threshold"}
    )
    if token_public_safe != "YES" and not cost_failures:
        cost_failures.append("token_public_safe_below_threshold")
    capability_failures = list(capability_gate.get("failures", []) or [])
    return {
        "performance": {"verdict": "PASS" if not performance_failures else "FAIL", "failures": performance_failures},
        "wearing": {"verdict": "PASS" if not wearing_failures else "FAIL", "failures": wearing_failures},
        "capability": {"verdict": str(capability_gate.get("verdict") or "FAIL"), "failures": capability_failures},
        "cost": {"verdict": "PASS" if not cost_failures else "FAIL", "failures": cost_failures},
    }


def _public_token_claim_status(a: dict[str, Any], b: dict[str, Any], *, min_rate: float = 0.8) -> str:
    try:
        without_rate = float(a.get("token_measured_rate", 0.0) or 0.0)
        with_rate = float(b.get("token_measured_rate", 0.0) or 0.0)
    except (TypeError, ValueError):
        return "NO"
    return "YES" if without_rate >= min_rate and with_rate >= min_rate else "NO"


def _capability_label(row: dict[str, Any]) -> str:
    if bool(row.get("rlm_trace_present")) or bool(row.get("capability_self_heal_used")) or bool(row.get("llm_self_heal_used")):
        return "RLM / self-heal"
    public_caps = _row_public_safe_capabilities(row)
    if "autoreason" in public_caps:
        return "Artifact / Claim + Autoreason"
    if {"artifact_gate", "claim_gate"} & public_caps:
        return "Artifact / Claim"
    text = " ".join(
        str(row.get(key) or "")
        for key in ("task_id", "category", "task_type", "fixture_kind", "task_desc", "success_criteria")
    ).lower()
    if any(token in text for token in ("belief", "confidence", "memory", "prior", "history")):
        return "Belief / Memory"
    if any(token in text for token in ("governance", "scope", "mempalace", "policy")):
        return "MemPalace / governance"
    if any(token in text for token in ("evidence", "artifact", "claim", "verify", "verification")):
        return "Artifact / Claim"
    if any(token in text for token in ("second", "round", "repair", "self-heal", "self_heal")):
        return "Repair verification"
    return "General"


def _row_public_safe_capabilities(row: dict[str, Any]) -> set[str]:
    receipts = row.get("capability_receipts")
    if isinstance(receipts, str):
        try:
            receipts = json.loads(receipts)
        except json.JSONDecodeError:
            receipts = []
    if not isinstance(receipts, list):
        return set()
    return public_safe_receipt_names(receipts)


def _pillar_win_rows(
    rows_without: list[dict[str, Any]],
    rows_with: list[dict[str, Any]],
) -> list[dict[str, str]]:
    without_by_key = {_task_trial_key(row): row for row in rows_without}
    wins: list[dict[str, str]] = []
    for row in rows_with:
        key = _task_trial_key(row)
        baseline = without_by_key.get(key, {})
        if _is_verified(row) and not _is_verified(baseline):
            wins.append(
                {
                    "task_id": str(row.get("task_id") or key[0]),
                    "trial": str(row.get("trial_index") or key[1]),
                    "capability": _capability_label(row),
                    "without": str(baseline.get("semantic_status") or baseline.get("status") or "UNKNOWN"),
                    "with": str(row.get("semantic_status") or row.get("status") or "UNKNOWN"),
                }
            )
    return wins


def _task_trial_key(row: dict[str, Any]) -> tuple[str, str]:
    return (str(row.get("task_id") or ""), str(row.get("trial_index") or "1"))


def _multiset_counts(rows: list[dict[str, Any]]) -> dict[tuple[str, str], int]:
    counts: dict[tuple[str, str], int] = {}
    for row in rows:
        key = _task_trial_key(row)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _route_quality_gate_from_rows(rows_with: list[dict[str, Any]]) -> list[str]:
    selected = 0.0
    invoked = 0.0
    evidence = 0.0
    outcome = 0.0
    for row in rows_with:
        counts = _row_route_quality_counts(row)
        if counts is None:
            selected += float(row.get("route_decision_selected_count", 0) or 0)
            invoked += float(row.get("route_decision_invoked_count", 0) or 0)
            evidence += float(row.get("route_decision_evidence_count", 0) or 0)
            outcome += float(row.get("route_decision_outcome_count", 0) or 0)
            continue
        selected += float(counts["selected"])
        invoked += float(counts["invoked"])
        evidence += float(counts["evidence"])
        outcome += float(counts["outcome"])
    if selected <= 0:
        return []
    selected_to_invoked = invoked / selected
    invoked_to_evidence = (evidence / invoked) if invoked > 0 else 0.0
    evidence_to_outcome = (outcome / evidence) if evidence > 0 else 0.0
    unnecessary_selected = max(selected - invoked, 0.0) / selected
    failures: list[str] = []
    if selected_to_invoked < _ROUTE_QUALITY_GATE_THRESHOLDS["selected_to_invoked_rate"]:
        failures.append("route_quality_selected_to_invoked_below_threshold")
    if invoked_to_evidence < _ROUTE_QUALITY_GATE_THRESHOLDS["invoked_to_evidence_rate"]:
        failures.append("route_quality_invoked_to_evidence_below_threshold")
    if evidence_to_outcome < _ROUTE_QUALITY_GATE_THRESHOLDS["evidence_to_outcome_rate"]:
        failures.append("route_quality_evidence_to_outcome_below_threshold")
    if unnecessary_selected > _ROUTE_QUALITY_GATE_THRESHOLDS["unnecessary_selected_rate_max"]:
        failures.append("route_quality_unnecessary_selected_above_threshold")
    for row in rows_with:
        preflight = _jsonish(row.get("research_preflight"), {})
        preflight = preflight if isinstance(preflight, dict) else {}
        status = str(row.get("semantic_status") or row.get("status") or "").upper()
        if bool(preflight.get("blocked")) and status in {"SUCCESS", "VERIFIED"}:
            failures.append("research_preflight_blocked_but_claimed_success")
        for receipt in _research_receipts(row):
            selected = bool(receipt.get("selected", receipt.get("selected_count", 0)))
            invoked = bool(receipt.get("invoked", receipt.get("invoked_count", 0)))
            evidence = bool(receipt.get("evidence_present") or receipt.get("evidence") or receipt.get("evidence_count", 0))
            gate = bool(receipt.get("gate_passed") or receipt.get("gate") or receipt.get("gate_count", 0))
            if selected and invoked and not evidence:
                failures.append("research_evidence_missing")
            if evidence and not gate:
                failures.append("research_gate_missing")
    return failures


def _public_claim_gate(
    *,
    rows_without: list[dict[str, Any]],
    rows_with: list[dict[str, Any]],
    summary_without: dict[str, Any],
    summary_with: dict[str, Any],
    formal: dict[str, Any],
    min_token_rate: float = 0.8,
    min_nexus_valid_rate: float = 1.0,
) -> dict[str, Any]:
    failures: list[str] = []
    if any(str(row.get("parallel_arms_mode") or "") == "smoke-only" for row in [*rows_without, *rows_with]):
        failures.append("parallel_smoke")
    if not rows_without or not rows_with:
        failures.append("missing_rows")
    if _multiset_counts(rows_without) != _multiset_counts(rows_with):
        failures.append("task_trial_mismatch")
    if _run_eligible_count(rows_without) != len(rows_without) or _run_eligible_count(rows_with) != len(rows_with):
        failures.append("run_eligibility_incomplete")
    try:
        if float(summary_without.get("token_measured_rate", 0.0) or 0.0) < min_token_rate:
            failures.append("without_token_measured_below_threshold")
        if float(summary_with.get("token_measured_rate", 0.0) or 0.0) < min_token_rate:
            failures.append("with_token_measured_below_threshold")
        if float(formal.get("valid_rate", 0.0) or 0.0) < min_nexus_valid_rate:
            failures.append("nexus_wearing_below_threshold")
        if float(summary_with.get("model_uses_nexus_rate", summary_with.get("gemini_uses_nexus_rate", 0.0)) or 0.0) < min_nexus_valid_rate:
            failures.append("model_uses_nexus_below_threshold")
        if float(summary_with.get("nexus_usage_valid_rate", 0.0) or 0.0) < min_nexus_valid_rate:
            failures.append("nexus_usage_valid_below_threshold")
        if float(summary_with.get("phase_completion_rate", 0.0) or 0.0) < min_nexus_valid_rate:
            failures.append("phase_completion_below_threshold")
        if float(summary_with.get("claim_verified_rate", 0.0) or 0.0) < min_nexus_valid_rate:
            failures.append("claim_verified_below_threshold")
        if float(summary_with.get("trust_mismatch_rate", 0.0) or 0.0) > 0.0:
            failures.append("with_trust_mismatch_above_zero")
    except (TypeError, ValueError):
        failures.append("metric_parse_error")
    for row in rows_with:
        if not str(row.get("route_decision_schema_version") or "").strip():
            task_id = str(row.get("task_id") or "unknown")
            failures.append(f"route_decision_missing:{task_id}")
        if "brain_hub_guidance_present" in row and not bool(row.get("brain_hub_guidance_present", False)):
            task_id = str(row.get("task_id") or "unknown")
            failures.append(f"brain_hub_guidance_missing:{task_id}")
        if "brain_hub_guidance_audit_passed" in row and not bool(row.get("brain_hub_guidance_audit_passed", False)):
            task_id = str(row.get("task_id") or "unknown")
            failures.append(f"brain_hub_guidance_audit_failed:{task_id}")
    rlm_rows = [row for row in rows_with if row.get("rlm_trace_present")]
    for row in rlm_rows:
        submit_count = int(row.get("rlm_submit_count", 0) or 0)
        verified_count = int(row.get("rlm_verified_count", 0) or 0)
        audit_rejected_count = int(row.get("rlm_audit_rejected_count", 0) or 0)
        trace_quality = int(row.get("rlm_trace_quality_score", 0) or 0)
        if submit_count > 0 and verified_count + audit_rejected_count <= 0:
            failures.append("rlm_submit_without_a_gate")
        if str(row.get("status") or row.get("semantic_status") or "") == "SUCCESS" and submit_count > 0 and verified_count <= 0:
            failures.append("rlm_success_without_verified_trace")
        if trace_quality < 60:
            failures.append("rlm_trace_quality_below_threshold")
        if bool(row.get("rlm_loop_phase") == "X") and not bool(row.get("rlm_x_loop_budget_observed", False)):
            failures.append("rlm_x_loop_budget_missing")
    for row in rows_with:
        expected = row.get("expected_capabilities") or []
        if isinstance(expected, str):
            try:
                expected = json.loads(expected)
            except json.JSONDecodeError:
                expected = []
        if not expected:
            continue
        coverage = row.get("expected_capability_receipt_coverage") or {}
        if isinstance(coverage, str):
            try:
                coverage = json.loads(coverage)
            except json.JSONDecodeError:
                coverage = {}
        if not isinstance(coverage, dict):
            failures.append("expected_capability_coverage_invalid")
            continue
        missing = coverage.get("missing") or []
        if missing:
            task_id = str(row.get("task_id") or "unknown")
            failures.append(f"expected_capability_not_public_safe:{task_id}:{','.join(str(item) for item in missing)}")
        elif not bool(coverage.get("all_public_safe", False)):
            task_id = str(row.get("task_id") or "unknown")
            failures.append(f"expected_capability_coverage_incomplete:{task_id}")
    failures.extend(_route_quality_gate_from_rows(rows_with))
    return {
        "verdict": "PASS" if not failures else "FAIL",
        "failures": sorted(set(failures)),
    }


def render_markdown_report(
    *,
    without_path: str,
    with_path: str,
    label_without: str,
    label_with: str,
    benchmark_date: str,
) -> str:
    rows_without = load_runs(without_path)
    rows_with = load_runs(with_path)
    report = compare_datasets(
        label_without,
        rows_without,
        label_with,
        rows_with,
    )
    a = report["a"]["summary"]
    b = report["b"]["summary"]
    delta = report["delta"]
    formal = report["formal_treatment"]
    wall_delta = float(delta["avg_wall_duration_sec_delta"])
    baseline_wall = float(a["avg_wall_duration_sec"])
    token_without = _token_status_counts(rows_without)
    token_with = _token_status_counts(rows_with)
    without_scope = _scope_summary(rows_without)
    with_scope = _scope_summary(rows_with)
    token_public_safe = _public_token_claim_status(a, b)
    infra_without = _infra_invalid_counts(rows_without)
    infra_with = _infra_invalid_counts(rows_with)
    eligible_without = _run_eligible_count(rows_without)
    eligible_with = _run_eligible_count(rows_with)
    eligible_solve_without = _eligible_solve_rate(rows_without)
    eligible_solve_with = _eligible_solve_rate(rows_with)
    eligible_solve_delta = eligible_solve_with - eligible_solve_without
    pillar_wins = _pillar_win_rows(rows_without, rows_with)
    public_gate = _public_claim_gate(
        rows_without=rows_without,
        rows_with=rows_with,
        summary_without=a,
        summary_with=b,
        formal=formal,
    )
    capability_gate = _per_capability_public_gate(report)
    route_quality_without = _route_quality_metrics(report, "a")
    route_quality_with = _route_quality_metrics(report, "b")
    route_tactical_without = _route_tactical_metrics(rows_without)
    route_tactical_with = _route_tactical_metrics(rows_with)
    research_preflight_without = _research_preflight_metrics(rows_without)
    research_preflight_with = _research_preflight_metrics(rows_with)
    brain_hub_without = _brain_hub_guidance_metrics(rows_without)
    brain_hub_with = _brain_hub_guidance_metrics(rows_with)
    claim_gates = _claim_gate_breakdown(
        public_gate=public_gate,
        capability_gate=capability_gate,
        token_public_safe=token_public_safe,
    )
    gate_failures = public_gate["failures"]
    solve_delta = float(eligible_solve_delta)
    if solve_delta > 0:
        public_claim_text = (
            f"On this fixed benchmark set, `{label_with}` improved eligible solve rate from "
            f"{_pct(eligible_solve_without)} to {_pct(eligible_solve_with)} "
            f"({_pct(eligible_solve_delta)} absolute) while keeping trust mismatch at "
            f"{_pct(b['trust_mismatch_rate'])}."
        )
    elif solve_delta == 0:
        public_claim_text = (
            f"On this fixed benchmark set, `{label_with}` matched eligible solve rate at "
            f"{_pct(eligible_solve_with)} while providing Nexus wearing evidence for "
            f"{formal['valid_count']}/{formal['total_runs']} rows and keeping trust mismatch at "
            f"{_pct(b['trust_mismatch_rate'])}."
        )
    else:
        public_claim_text = (
            f"On this fixed benchmark set, `{label_with}` reduced eligible solve rate from "
            f"{_pct(eligible_solve_without)} to {_pct(eligible_solve_with)} "
            f"({_pct(eligible_solve_delta)} absolute); no positive solve-rate claim is allowed."
        )
    if public_gate["verdict"] != "PASS":
        public_claim_text = (
            "No public performance claim is allowed from this run because the public claim gate failed. "
            f"Failures: {_reasons_text({reason: 1 for reason in gate_failures})}."
        )

    lines = [
        f"# {label_with} Benchmark Report",
        "",
        f"- Date: {benchmark_date}",
        f"- Baseline: `{label_without}`",
        f"- Treatment: `{label_with}`",
        f"- Without Nexus: `{without_path}`",
        f"- With Nexus: `{with_path}`",
        f"- Without Nexus scope: {without_scope['unique_tasks']} unique tasks x {without_scope['repeat_trials']} trials = {without_scope['rows']} rows",
        f"- With Nexus scope: {with_scope['unique_tasks']} unique tasks x {with_scope['repeat_trials']} trials = {with_scope['rows']} rows",
        "",
        "## Result",
        "",
        "| Metric | Without Nexus | With Nexus | Delta |",
        "| --- | ---: | ---: | ---: |",
        f"| Usable rows | {eligible_without}/{without_scope['rows']} | {eligible_with}/{with_scope['rows']} | n/a |",
        f"| Infra invalid rows | {without_scope['rows'] - eligible_without} | {with_scope['rows'] - eligible_with} | n/a |",
        f"| Solve rate | {_pct(a['solve_rate'])} | {_pct(b['solve_rate'])} | {_pct(delta['solve_rate_delta'])} |",
        f"| Eligible solve rate | {_pct(eligible_solve_without)} | {_pct(eligible_solve_with)} | {_pct(eligible_solve_delta)} |",
        f"| Semantic verified | {_pct(a['semantic_verified_rate'])} | {_pct(b['semantic_verified_rate'])} | {_pct(delta['semantic_verified_rate_delta'])} |",
        f"| Trust mismatch | {_pct(a['trust_mismatch_rate'])} | {_pct(b['trust_mismatch_rate'])} | {_pct(delta['trust_mismatch_rate_delta'])} |",
        f"| Avg wall time | {_num(a['avg_wall_duration_sec'])}s | {_num(b['avg_wall_duration_sec'])}s | {_num(wall_delta)}s |",
        f"| Wall speedup | n/a | {_wall_speedup(wall_delta, baseline_wall)} | n/a |",
        f"| Avg model calls | {_num(a['avg_model_calls'])} | {_num(b['avg_model_calls'])} | {_num(delta['avg_model_calls_delta'])} |",
        f"| Token measured rate | {_pct(a['token_measured_rate'])} | {_pct(b['token_measured_rate'])} | {_pct(delta['token_measured_rate_delta'])} |",
        f"| Token local-only rate | {_pct(a['token_local_only_rate'])} | {_pct(b['token_local_only_rate'])} | {_pct(delta['token_local_only_rate_delta'])} |",
        f"| Cost-comparable rate | {_pct(a['cost_comparable_rate'])} | {_pct(b['cost_comparable_rate'])} | {_pct(delta['cost_comparable_rate_delta'])} |",
        f"| Model token measured rate | {_pct(a['model_token_measured_rate'])} | {_pct(b['model_token_measured_rate'])} | {_pct(delta['model_token_measured_rate_delta'])} |",
        f"| Gateway stats source rate | {_pct(a['gateway_stats_source_rate'])} | {_pct(b['gateway_stats_source_rate'])} | {_pct(delta['gateway_stats_source_rate_delta'])} |",
        f"| Gateway usage metadata source rate | {_pct(a['gateway_usage_metadata_source_rate'])} | {_pct(b['gateway_usage_metadata_source_rate'])} | {_pct(delta['gateway_usage_metadata_source_rate_delta'])} |",
        f"| Local rescue rate | {_pct(a['local_rescue_rate'])} | {_pct(b['local_rescue_rate'])} | {_pct(delta['local_rescue_rate_delta'])} |",
        f"| Guard fallback rate | {_pct(a['guard_fallback_rate'])} | {_pct(b['guard_fallback_rate'])} | {_pct(delta['guard_fallback_rate_delta'])} |",
        f"| Verification rescue rate | {_pct(a['verification_rescue_rate'])} | {_pct(b['verification_rescue_rate'])} | {_pct(delta['verification_rescue_rate_delta'])} |",
        f"| LLM self-heal rate | {_pct(a['llm_self_heal_rate'])} | {_pct(b['llm_self_heal_rate'])} | {_pct(delta['llm_self_heal_rate_delta'])} |",
        f"| RLM trace present | {_pct(a['rlm_trace_present_rate'])} | {_pct(b['rlm_trace_present_rate'])} | {_pct(delta['rlm_trace_present_rate_delta'])} |",
        f"| RLM trace quality | {_num(a['avg_rlm_trace_quality_score'])} | {_num(b['avg_rlm_trace_quality_score'])} | {_num(delta['avg_rlm_trace_quality_score_delta'])} |",
        f"| Token public-safe claim | {token_public_safe} | {token_public_safe} | n/a |",
        "",
        "## Trustworthy Delivery KPIs",
        "",
        "| KPI | Without Nexus | With Nexus | Delta | Public interpretation |",
        "| --- | ---: | ---: | ---: | --- |",
        f"| Time-to-Verified | {_num(a['avg_time_to_verified_sec'])}s | {_num(b['avg_time_to_verified_sec'])}s | {_num(delta['avg_time_to_verified_sec_delta'])}s | Lower is faster among verified rows |",
        f"| Fail-closed block rate | {_pct(a['fail_closed_block_rate'])} | {_pct(b['fail_closed_block_rate'])} | {_pct(delta['fail_closed_block_rate_delta'])} | Higher can be desirable when blocking unsafe/unsupported claims |",
        f"| Replay observed rate | {_pct(a['replay_observed_rate'])} | {_pct(b['replay_observed_rate'])} | {_pct(delta['replay_observed_rate_delta'])} | Replay evidence availability |",
        f"| Replay pass rate | {_pct(a['replay_pass_rate'])} | {_pct(b['replay_pass_rate'])} | {_pct(delta['replay_pass_rate_delta'])} | Pass rate among rows with replay evidence |",
        f"| Policy-hit success rate | {_pct(a['policy_hit_success_rate'])} | {_pct(b['policy_hit_success_rate'])} | {_pct(delta['policy_hit_success_rate_delta'])} | Success after policy/memory/governance hit |",
        f"| Policy-hit lift within arm | {_pct(a['policy_hit_success_lift'])} | {_pct(b['policy_hit_success_lift'])} | {_pct(delta['policy_hit_success_lift_delta'])} | Policy-hit rows vs non-policy rows |",
        f"| 7-day onboarding success | observation | observation | n/a | Requires separate onboarding suite, not single-run A/B |",
        "",
        "## Five-Pillar Contribution",
        "",
        "| Pillar | Without Nexus | With Nexus | Delta | Evidence signal |",
        "| --- | ---: | ---: | ---: | --- |",
        f"| LanceDB | {_pct(a['pillar_lancedb_active_rate'])} | {_pct(b['pillar_lancedb_active_rate'])} | {_pct(b['pillar_lancedb_active_rate'] - a['pillar_lancedb_active_rate'])} | tactical retrieval active |",
        f"| Memory | {_pct(a['pillar_memory_active_rate'])} | {_pct(b['pillar_memory_active_rate'])} | {_pct(b['pillar_memory_active_rate'] - a['pillar_memory_active_rate'])} | prior lessons/hits active |",
        f"| MemPalace | {_pct(a['pillar_mempalace_active_rate'])} | {_pct(b['pillar_mempalace_active_rate'])} | {_pct(b['pillar_mempalace_active_rate'] - a['pillar_mempalace_active_rate'])} | governance boundary active |",
        f"| Belief | {_pct(a['pillar_belief_active_rate'])} | {_pct(b['pillar_belief_active_rate'])} | {_pct(b['pillar_belief_active_rate'] - a['pillar_belief_active_rate'])} | confidence/budget signal active |",
        f"| Artifact / Claim | {_pct(a['pillar_artifact_active_rate'])} | {_pct(b['pillar_artifact_active_rate'])} | {_pct(b['pillar_artifact_active_rate'] - a['pillar_artifact_active_rate'])} | artifact checks + claim verification |",
        f"| Claim verified | {_pct(a['claim_verified_rate'])} | {_pct(b['claim_verified_rate'])} | {_pct(delta['claim_verified_rate_delta'])} | A/C acceptance evidence |",
        "",
        "## MSA / Orchestration Trace",
        "",
        "| Capability | Without Nexus | With Nexus | Delta | Evidence signal |",
        "| --- | ---: | ---: | ---: | --- |",
        f"| Hyper | {_pct(a['hyper_used_rate'])} | {_pct(b['hyper_used_rate'])} | {_pct(delta['hyper_used_rate_delta'])} | focused sprint route active |",
        f"| Self-heal | {_pct(a['self_heal_used_rate'])} | {_pct(b['self_heal_used_rate'])} | {_pct(delta['self_heal_used_rate_delta'])} | repair loop/self-heal active |",
        f"| Swarm | {_pct(a['swarm_used_rate'])} | {_pct(b['swarm_used_rate'])} | {_pct(delta['swarm_used_rate_delta'])} | evidence-backed swarm sandbox used |",
        f"| Drone | {_pct(a['drone_used_rate'])} | {_pct(b['drone_used_rate'])} | {_pct(delta['drone_used_rate_delta'])} | delegated worker/drone used |",
        f"| Nightshift recommended | {_pct(a['nightshift_recommended_rate'])} | {_pct(b['nightshift_recommended_rate'])} | {_pct(delta['nightshift_recommended_rate_delta'])} | escalation recommended |",
        f"| Nightshift invoked | {_pct(a['nightshift_invoked_rate'])} | {_pct(b['nightshift_invoked_rate'])} | {_pct(delta['nightshift_invoked_rate_delta'])} | nightshift report evidence exists |",
        f"| Nightshift recovered | {_pct(a['nightshift_recovery_rate'])} | {_pct(b['nightshift_recovery_rate'])} | {_pct(delta['nightshift_recovery_rate_delta'])} | nightshift recovery verified |",
        f"| Autoreason | {_pct(a['autoreason_enabled_rate'])} | {_pct(b['autoreason_enabled_rate'])} | {_pct(delta['autoreason_enabled_rate_delta'])} | candidate judge active |",
        f"| DDTree enabled | {_pct(a['ddtree_enabled_rate'])} | {_pct(b['ddtree_enabled_rate'])} | {_pct(delta['ddtree_enabled_rate_delta'])} | candidate pruning layer active |",
        f"| DDTree eligible | {_pct(a['ddtree_eligible_rate'])} | {_pct(b['ddtree_eligible_rate'])} | {_pct(delta['ddtree_eligible_rate_delta'])} | enough candidates for pruning |",
        f"| Ultra Review recommended | {_pct(a['ultra_review_recommended_rate'])} | {_pct(b['ultra_review_recommended_rate'])} | {_pct(delta['ultra_review_recommended_rate_delta'])} | high-risk governance route selected |",
        f"| Ultra Review invoked | {_pct(a['ultra_review_invoked_rate'])} | {_pct(b['ultra_review_invoked_rate'])} | {_pct(delta['ultra_review_invoked_rate_delta'])} | high-risk dry gate executed |",
        f"| Capability plan trace | {_pct(a['capability_plan_trace_present_rate'])} | {_pct(b['capability_plan_trace_present_rate'])} | {_pct(delta['capability_plan_trace_present_rate_delta'])} | constrained composition dry-run present |",
        f"| Capability plan nodes | {_num(a['avg_capability_plan_node_count'])} | {_num(b['avg_capability_plan_node_count'])} | {_num(delta['avg_capability_plan_node_count_delta'])} | average planned capability nodes |",
        f"| Capability plan score | {_num(a['avg_capability_plan_score'])} | {_num(b['avg_capability_plan_score'])} | {_num(delta['avg_capability_plan_score_delta'])} | benefit-risk-cost score |",
        f"| RLM trace present | {_pct(a['rlm_trace_present_rate'])} | {_pct(b['rlm_trace_present_rate'])} | {_pct(delta['rlm_trace_present_rate_delta'])} | recursive trace emitted |",
        f"| RLM trace quality | {_num(a['avg_rlm_trace_quality_score'])} | {_num(b['avg_rlm_trace_quality_score'])} | {_num(delta['avg_rlm_trace_quality_score_delta'])} | trace has submit/A-gate/evidence signal |",
        "",
        "## Brain Hub Guidance",
        "",
        "| Metric | Without Nexus | With Nexus | Delta | Meaning |",
        "| --- | ---: | ---: | ---: | --- |",
        f"| Guidance present | {_pct(brain_hub_without['present_rate'])} | {_pct(brain_hub_with['present_rate'])} | {_pct(brain_hub_with['present_rate'] - brain_hub_without['present_rate'])} | Route row includes Brain Hub guidance receipt |",
        f"| Reality audit passed | {_pct(brain_hub_without['audit_passed_rate'])} | {_pct(brain_hub_with['audit_passed_rate'])} | {_pct(brain_hub_with['audit_passed_rate'] - brain_hub_without['audit_passed_rate'])} | Brain Hub doc/runtime audit passed before claim |",
        f"| Avg documents indexed | {_num(brain_hub_without['document_avg_count'])} | {_num(brain_hub_with['document_avg_count'])} | {_num(brain_hub_with['document_avg_count'] - brain_hub_without['document_avg_count'])} | Average Brain Hub documents available to route |",
        f"| Audit failure count | {_num(brain_hub_without['failure_count'], 0)} | {_num(brain_hub_with['failure_count'], 0)} | {_num(brain_hub_with['failure_count'] - brain_hub_without['failure_count'], 0)} | Lower means fewer doc-code reality gaps |",
        f"| Guidance phases | {', '.join(brain_hub_without['phases']) or 'none'} | {', '.join(brain_hub_with['phases']) or 'none'} | n/a | Phase guidance exposed to route |",
        "",
        "## Capability Coverage Matrix",
        "",
        "| Capability | Selected | Invoked | Evidence | Gate | Outcome | Public safe | Source | Failure reasons |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |",
        *_capability_coverage_rows(report),
        "",
        "## Route Quality",
        "",
        "| Metric | Without Nexus | With Nexus | Delta | Meaning |",
        "| --- | ---: | ---: | ---: | --- |",
        f"| Selected -> Invoked | {_pct(route_quality_without['selected_to_invoked_rate'])} | {_pct(route_quality_with['selected_to_invoked_rate'])} | {_pct(route_quality_with['selected_to_invoked_rate'] - route_quality_without['selected_to_invoked_rate'])} | Higher means selected capabilities are actually executed |",
        f"| Invoked -> Evidence | {_pct(route_quality_without['invoked_to_evidence_rate'])} | {_pct(route_quality_with['invoked_to_evidence_rate'])} | {_pct(route_quality_with['invoked_to_evidence_rate'] - route_quality_without['invoked_to_evidence_rate'])} | Higher means execution is evidenced |",
        f"| Evidence -> Outcome | {_pct(route_quality_without['evidence_to_outcome_rate'])} | {_pct(route_quality_with['evidence_to_outcome_rate'])} | {_pct(route_quality_with['evidence_to_outcome_rate'] - route_quality_without['evidence_to_outcome_rate'])} | Higher means evidence contributes to verified outcomes |",
        f"| Unnecessary Selected | {_pct(route_quality_without['unnecessary_selected_rate'])} | {_pct(route_quality_with['unnecessary_selected_rate'])} | {_pct(route_quality_with['unnecessary_selected_rate'] - route_quality_without['unnecessary_selected_rate'])} | Lower means less over-selection friction |",
        f"| Tactical trace present | {_pct(route_tactical_without['trace_present_rate'])} | {_pct(route_tactical_with['trace_present_rate'])} | {_pct(route_tactical_with['trace_present_rate'] - route_tactical_without['trace_present_rate'])} | Route tactical sequence is exported into OpenSeeker telemetry |",
        f"| Avg tactical tools | {_num(route_tactical_without['avg_route_tactical_tool_count'])} | {_num(route_tactical_with['avg_route_tactical_tool_count'])} | {_num(route_tactical_with['avg_route_tactical_tool_count'] - route_tactical_without['avg_route_tactical_tool_count'])} | Planned tactical tool actions per traced row |",
        f"| Avg evidence-required tools | {_num(route_tactical_without['avg_route_evidence_required_count'])} | {_num(route_tactical_with['avg_route_evidence_required_count'])} | {_num(route_tactical_with['avg_route_evidence_required_count'] - route_tactical_without['avg_route_evidence_required_count'])} | Tactical tools that must emit evidence receipts |",
        f"| Runtime pruned capabilities | {_pct(a['runtime_pruned_capability_rate'])} | {_pct(b['runtime_pruned_capability_rate'])} | {_pct(delta['runtime_pruned_capability_rate_delta'])} | Selected capabilities removed from public receipts because runtime executor readiness was absent |",
        f"| Avg runtime pruned capabilities | {_num(a['avg_runtime_pruned_capability_count'])} | {_num(b['avg_runtime_pruned_capability_count'])} | {_num(delta['avg_runtime_pruned_capability_count_delta'])} | Lower means fewer planner/runtime mismatches |",
        f"| Research preflight present | {_pct(research_preflight_without['preflight_present_rate'])} | {_pct(research_preflight_with['preflight_present_rate'])} | {_pct(research_preflight_with['preflight_present_rate'] - research_preflight_without['preflight_present_rate'])} | Route emitted a research preflight decision |",
        f"| Research preflight blocked | {_pct(research_preflight_without['preflight_blocked_rate'])} | {_pct(research_preflight_with['preflight_blocked_rate'])} | {_pct(research_preflight_with['preflight_blocked_rate'] - research_preflight_without['preflight_blocked_rate'])} | Fail-closed before editing an unverified claim |",
        f"| Claim uncertainty caught | {_pct(research_preflight_without['claim_uncertainty_caught_rate'])} | {_pct(research_preflight_with['claim_uncertainty_caught_rate'])} | {_pct(research_preflight_with['claim_uncertainty_caught_rate'] - research_preflight_without['claim_uncertainty_caught_rate'])} | Research identified an assumption that needs evidence |",
        f"| Research evidence present | {_pct(research_preflight_without['research_evidence_present_rate'])} | {_pct(research_preflight_with['research_evidence_present_rate'])} | {_pct(research_preflight_with['research_evidence_present_rate'] - research_preflight_without['research_evidence_present_rate'])} | Research capability produced evidence |",
        f"| Research gate passed | {_pct(research_preflight_without['research_gate_passed_rate'])} | {_pct(research_preflight_with['research_gate_passed_rate'])} | {_pct(research_preflight_with['research_gate_passed_rate'] - research_preflight_without['research_gate_passed_rate'])} | Research evidence passed a route gate |",
        f"| Session ledger logged | {_pct(research_preflight_without['session_ledger_logged_rate'])} | {_pct(research_preflight_with['session_ledger_logged_rate'])} | {_pct(research_preflight_with['session_ledger_logged_rate'] - research_preflight_without['session_ledger_logged_rate'])} | Research session packet was logged for audit |",
        f"| Research doctor pass | {_pct(research_preflight_without['research_doctor_pass_rate'])} | {_pct(research_preflight_with['research_doctor_pass_rate'])} | {_pct(research_preflight_with['research_doctor_pass_rate'] - research_preflight_without['research_doctor_pass_rate'])} | Research runtime lint passed |",
        f"| Research doctor score | {_num(research_preflight_without['avg_research_doctor_score'])} | {_num(research_preflight_with['avg_research_doctor_score'])} | {_num(research_preflight_with['avg_research_doctor_score'] - research_preflight_without['avg_research_doctor_score'])} | Average research runtime lint score |",
        f"| Claim probe eligible | {_pct(research_preflight_without['claim_probe_eligible_rate'])} | {_pct(research_preflight_with['claim_probe_eligible_rate'])} | {_pct(research_preflight_with['claim_probe_eligible_rate'] - research_preflight_without['claim_probe_eligible_rate'])} | Tasks that required pre-patch claim probing |",
        f"| Claim probe gate pass | {_pct(research_preflight_without['claim_probe_gate_pass_rate'])} | {_pct(research_preflight_with['claim_probe_gate_pass_rate'])} | {_pct(research_preflight_with['claim_probe_gate_pass_rate'] - research_preflight_without['claim_probe_gate_pass_rate'])} | Eligible probes allowed the patch with evidence |",
        f"| Autoreason A/B/AB factory ready | {_pct(research_preflight_without['autoreason_ab_factory_ready_rate'])} | {_pct(research_preflight_with['autoreason_ab_factory_ready_rate'])} | {_pct(research_preflight_with['autoreason_ab_factory_ready_rate'] - research_preflight_without['autoreason_ab_factory_ready_rate'])} | Candidate tournament had A/B/AB roles |",
        f"| Autoreason AB winner | {_pct(research_preflight_without['autoreason_ab_winner_rate'])} | {_pct(research_preflight_with['autoreason_ab_winner_rate'])} | {_pct(research_preflight_with['autoreason_ab_winner_rate'] - research_preflight_without['autoreason_ab_winner_rate'])} | Synthesized candidate won blind Borda |",
        f"| Governance event present | {_pct(research_preflight_without['governance_event_present_rate'])} | {_pct(research_preflight_with['governance_event_present_rate'])} | {_pct(research_preflight_with['governance_event_present_rate'] - research_preflight_without['governance_event_present_rate'])} | Typed governance events reached benchmark rows |",
        f"| Governance event count | {_num(research_preflight_without['governance_event_avg_count'])} | {_num(research_preflight_with['governance_event_avg_count'])} | {_num(research_preflight_with['governance_event_avg_count'] - research_preflight_without['governance_event_avg_count'])} | Average typed governance events per row |",
        f"| Evidence accepted event | {_pct(research_preflight_without['evidence_accepted_event_rate'])} | {_pct(research_preflight_with['evidence_accepted_event_rate'])} | {_pct(research_preflight_with['evidence_accepted_event_rate'] - research_preflight_without['evidence_accepted_event_rate'])} | Verified artifacts emit evidence_accepted |",
        f"| Learning decision event | {_pct(research_preflight_without['learning_decision_event_rate'])} | {_pct(research_preflight_with['learning_decision_event_rate'])} | {_pct(research_preflight_with['learning_decision_event_rate'] - research_preflight_without['learning_decision_event_rate'])} | LearningSteward decision is visible to reports |",
        f"| Audit failed event | {_pct(research_preflight_without['audit_failed_event_rate'])} | {_pct(research_preflight_with['audit_failed_event_rate'])} | {_pct(research_preflight_with['audit_failed_event_rate'] - research_preflight_without['audit_failed_event_rate'])} | Failed evidence paths emit audit_failed |",
        "",
        "## Capability Activation Details",
        "",
        "| Capability | Status | Selected | Invoked | Evidence | Gate | Outcome | Source | Interpretation |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |",
        *_capability_activation_rows(report),
        "",
        "## Capability Win Map",
        "",
        "| Task | Trial | Capability | Without Nexus | With Nexus |",
        "| --- | ---: | --- | --- | --- |",
        *(
            [
                f"| {row['task_id']} | {row['trial']} | {row['capability']} | {row['without']} | {row['with']} |"
                for row in pillar_wins
            ]
            or ["| none | n/a | n/a | n/a | n/a |"]
        ),
        "",
        "## Token Telemetry",
        "",
        "| Token status | Without Nexus | With Nexus |",
        "| --- | ---: | ---: |",
        f"| measured | {_count_text(token_without, 'measured')} | {_count_text(token_with, 'measured')} |",
        f"| estimated | {_count_text(token_without, 'estimated')} | {_count_text(token_with, 'estimated')} |",
        f"| missing/unknown | {_count_text(token_without, 'missing')}/{_count_text(token_without, 'unknown')} | {_count_text(token_with, 'missing')}/{_count_text(token_with, 'unknown')} |",
        f"| not applicable local only | {_count_text(token_without, 'not_applicable_local_only')} | {_count_text(token_with, 'not_applicable_local_only')} |",
        "",
        "## Run Validity",
        "",
        f"- Public claim gate: {public_gate['verdict']}",
        f"- Public claim gate failures: {_reasons_text({reason: 1 for reason in gate_failures})}",
        f"- Performance claim gate: {claim_gates['performance']['verdict']}",
        f"- Performance claim gate failures: {_reasons_text({reason: 1 for reason in claim_gates['performance']['failures']})}",
        f"- Wearing claim gate: {claim_gates['wearing']['verdict']}",
        f"- Wearing claim gate failures: {_reasons_text({reason: 1 for reason in claim_gates['wearing']['failures']})}",
        f"- Capability-specific claim gate: {claim_gates['capability']['verdict']}",
        f"- Capability-specific claim gate failures: {_reasons_text({reason: 1 for reason in claim_gates['capability']['failures']})}",
        f"- Cost claim gate: {claim_gates['cost']['verdict']}",
        f"- Cost claim gate failures: {_reasons_text({reason: 1 for reason in claim_gates['cost']['failures']})}",
        f"- Per-capability public gate: {capability_gate['verdict']}",
        f"- Per-capability public-safe capabilities: {', '.join(capability_gate['public_safe']) if capability_gate['public_safe'] else 'none'}",
        f"- Per-capability gate failures: {_reasons_text({reason: 1 for reason in capability_gate['failures']})}",
        f"- Without Nexus usable rows: {eligible_without}/{without_scope['rows']}",
        f"- With Nexus usable rows: {eligible_with}/{with_scope['rows']}",
        f"- Without Nexus infra invalid reasons: {_reasons_text(infra_without)}",
        f"- With Nexus infra invalid reasons: {_reasons_text(infra_with)}",
        "",
        "## Nexus Wearing Evidence",
        "",
        f"- Formal treatment valid: {formal['valid_count']}/{formal['total_runs']} ({_pct(formal['valid_rate'])})",
        f"- Model uses Nexus rate: {_pct(b.get('model_uses_nexus_rate', b['gemini_uses_nexus_rate']))}",
        f"- Nexus usage valid rate: {_pct(b['nexus_usage_valid_rate'])}",
        f"- Phase completion rate: {_pct(b['phase_completion_rate'])}",
        f"- Claim verified rate: {_pct(b['claim_verified_rate'])}",
        f"- Nexus rescue rate: {_pct(b['nexus_rescue_rate'])}",
        f"- Guard fallback rate: {_pct(b['guard_fallback_rate'])}",
        f"- Verification rescue rate: {_pct(b['verification_rescue_rate'])}",
        f"- LLM self-heal rate: {_pct(b['llm_self_heal_rate'])}",
        "",
        "## Public-Safe Claim",
        "",
        public_claim_text,
        "",
        "## Limits",
        "",
        "- Token/cost claims are not public-safe unless token measured rate is high enough for both arms.",
        "- Small samples need repeated trials before publication-grade claims.",
        "- This report proves benchmark-row evidence, not broad production generalization.",
        "",
    ]
    return "\n".join(lines)


def evaluate_public_claim_gate(
    *,
    without_path: Path,
    with_path: Path,
    label_without: str,
    label_with: str,
) -> dict[str, Any]:
    rows_without = load_runs(without_path)
    rows_with = load_runs(with_path)
    report = compare_datasets(label_without, rows_without, label_with, rows_with)
    return _public_claim_gate(
        rows_without=rows_without,
        rows_with=rows_with,
        summary_without=report["a"]["summary"],
        summary_with=report["b"]["summary"],
        formal=report["formal_treatment"],
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Render Gemini bare vs Gemini+Nexus benchmark markdown.")
    parser.add_argument("--without", required=True, help="Without-Nexus JSON/JSONL/CSV path")
    parser.add_argument("--with-nexus", required=True, help="With-Nexus JSON/JSONL/CSV path")
    parser.add_argument("--label-without", default="gemini_3_flash_bare")
    parser.add_argument("--label-with", default="gemini_3_flash_nexus")
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--output", required=True, help="Markdown output path")
    parser.add_argument(
        "--enforce-public-gate",
        action="store_true",
        help="Exit non-zero when the public claim gate is not PASS.",
    )
    args = parser.parse_args()

    public_gate = evaluate_public_claim_gate(
        without_path=Path(args.without),
        with_path=Path(args.with_nexus),
        label_without=args.label_without,
        label_with=args.label_with,
    )
    markdown = render_markdown_report(
        without_path=args.without,
        with_path=args.with_nexus,
        label_without=args.label_without,
        label_with=args.label_with,
        benchmark_date=args.date,
    )
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(markdown, encoding="utf-8")
    print(str(out))
    if args.enforce_public_gate and public_gate.get("verdict") != "PASS":
        print(f"public_claim_gate={public_gate.get('verdict')} failures={','.join(public_gate.get('failures', []))}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
