from __future__ import annotations

from typing import Any
import json

from nexus.engine.capability_aliases import normalize_capability_name, normalize_capability_names, normalize_capability_receipt


PUBLIC_CLAIM_CAPABILITIES = frozenset(
    {
        "autoreason",
        "codeintel",
        "ddtree",
        "drone",
        "judge_panel",
        "nightshift",
        "swarm",
        "ultra_review",
    }
)

INTERNAL_MARKER_CAPABILITIES = frozenset(
    {
        "acceptance_check",
        "learn_mode",
        "learn_phase_slo",
        "plan_quality_gate",
        "pregate",
        "research_route",
        "sandbox",
    }
)

REQUIRED_NINE_CAPABILITIES = frozenset(
    {
        "autoreason",
        "ddtree",
        "ultra_review",
        "research",
        "lancedb",
        "swarm",
        "drone",
        "nightshift",
        "belief",
    }
)

REQUIRED_ROUTE_RUNTIME_CAPABILITIES = frozenset(
    {
        *REQUIRED_NINE_CAPABILITIES,
        "semantic_searcher",
        "swarm_quiet_moment",
    }
)

ROUTE_QUALITY_THRESHOLDS = {
    "selected_to_invoked_rate": 0.70,
    "invoked_to_evidence_rate": 0.95,
    "evidence_to_outcome_rate": 0.90,
    "unnecessary_selected_rate_max": 0.30,
}

RECEIPT_BACKED_CAPABILITIES = frozenset(
    {
        "artifact_gate",
        "acceptance_check",
        "architecture_scout",
        "asi_constraint_extractor",
        "autonomic_router",
        "autoreason",
        "benchmark",
        "belief",
        "claim_gate",
        "codeintel",
        "ddtree",
        "delivery_gate",
        "direct_mode",
        "drone",
        "external_doc_scout",
        "federation",
        "file_lock",
        "forecast_gate",
        "formal_report",
        "bdd_acceptance_skill",
        "harness_preflight_sensor",
        "hyper",
        "integration_manager",
        "jit_validation",
        "judge_panel",
        "lancedb",
        "learn_mode",
        "learn_phase_slo",
        "learn_scheduler",
        "local_heal",
        "memory",
        "mempalace_gate",
        "meta_opt",
        "metabolism",
        "msa_router",
        "multi_agent",
        "nightshift",
        "oracle_shadow",
        "plan_quality_gate",
        "pregate",
        "repair_loop",
        "research",
        "research_control_plane",
        "research_route",
        "registry_sync",
        "sandbox",
        "semantic_failure_sensor",
        "semantic_searcher",
        "stress_test",
        "swarm",
        "swarm_quiet_moment",
        "ultra_review",
        "ui_validator",
        "xray",
    }
)

NON_ACTIONABLE_CAPABILITY_REASONS = frozenset(
    {
        "direct_codex_no_ultra_review_report",
        "feature_flag_disabled",
        "no_pruning_opportunity",
        "pending_executor",
        "recommended_without_invocation",
    }
)

CAPABILITY_NON_ACTIONABLE_REASONS = {
    "ddtree": frozenset({"selected_without_invocation"}),
}

CAPABILITY_PUBLIC_GATE_NON_ACTIONABLE_REASONS = {
    "autoreason": frozenset({"selected_without_invocation"}),
}


def is_public_claim_capability(name: Any) -> bool:
    return normalize_capability_name(name) in PUBLIC_CLAIM_CAPABILITIES


def is_receipt_backed_capability(name: Any) -> bool:
    return normalize_capability_name(name) in RECEIPT_BACKED_CAPABILITIES


def is_internal_marker_capability(name: Any) -> bool:
    return normalize_capability_name(name) in INTERNAL_MARKER_CAPABILITIES


def route_quality_ignored_reasons(name: Any) -> set[str]:
    normalized = normalize_capability_name(name)
    return set(NON_ACTIONABLE_CAPABILITY_REASONS) | set(CAPABILITY_NON_ACTIONABLE_REASONS.get(normalized, frozenset()))


def public_gate_ignored_reasons(name: Any) -> set[str]:
    normalized = normalize_capability_name(name)
    return route_quality_ignored_reasons(normalized) | set(
        CAPABILITY_PUBLIC_GATE_NON_ACTIONABLE_REASONS.get(normalized, frozenset())
    )


def receipt_has_runtime_signal(receipt: dict[str, Any]) -> bool:
    return any(
        bool(receipt.get(key))
        for key in ("invoked", "evidence_present", "evidence", "gate_passed", "gate", "outcome_contributed")
    )


def is_route_quality_actionable_receipt(receipt: dict[str, Any]) -> bool:
    name = normalize_capability_name(receipt.get("name") or receipt.get("capability"))
    if not name:
        return False
    if is_internal_marker_capability(name):
        return False
    if bool(receipt.get("public_claim_safe")):
        return True
    if receipt_has_runtime_signal(receipt):
        return True
    if not is_public_claim_capability(name):
        return False
    if not bool(receipt.get("selected", False)):
        return False
    reason = str(receipt.get("failure_reason") or "").strip()
    return not (reason and reason in route_quality_ignored_reasons(name))


def public_safe_receipt_names(receipts: Any) -> set[str]:
    if not isinstance(receipts, list):
        return set()
    names: set[str] = set()
    for receipt in receipts:
        if not isinstance(receipt, dict) or not bool(receipt.get("public_claim_safe")):
            continue
        name = normalize_capability_name(receipt.get("name") or receipt.get("capability"))
        if name:
            names.add(name)
    return names


def jsonish(value: Any, fallback: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return fallback
    return value if value is not None else fallback


def route_tactical_tool_map(row: dict[str, Any]) -> list[dict[str, Any]]:
    payload = jsonish(row.get("route_tactical_tool_map"), [])
    if not isinstance(payload, list) or not payload:
        payload = jsonish(row.get("route_tactical_tool_map_json"), [])
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def route_quality_counts_from_row(row: dict[str, Any]) -> dict[str, int] | None:
    receipts = jsonish(row.get("capability_receipts"), [])
    tactical_map = route_tactical_tool_map(row)
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
        if not is_route_quality_actionable_receipt(receipt):
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


def expected_capability_receipt_coverage(
    *,
    expected_capabilities: Any,
    capability_receipts: Any,
) -> dict[str, Any]:
    normalized_receipts = [
        normalize_capability_receipt(item)
        for item in (capability_receipts or [])
        if isinstance(item, dict) and str(item.get("name") or item.get("capability") or "").strip()
    ]
    receipts = {normalize_capability_name(item.get("name") or item.get("capability")): item for item in normalized_receipts}
    expected = normalize_capability_names(expected_capabilities)
    public_safe: list[str] = []
    missing: list[str] = []
    failure_reasons: dict[str, str] = {}
    for capability in expected:
        receipt = receipts.get(capability)
        if not receipt:
            missing.append(capability)
            failure_reasons[capability] = "missing_receipt"
            continue
        if bool(receipt.get("public_claim_safe")):
            public_safe.append(capability)
            continue
        missing.append(capability)
        failure_reasons[capability] = str(receipt.get("failure_reason") or "receipt_not_public_safe")
    return {
        "expected": expected,
        "public_safe": public_safe,
        "missing": missing,
        "failure_reasons": failure_reasons,
        "all_public_safe": bool(expected) and not missing,
    }
