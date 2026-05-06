from __future__ import annotations

from typing import Any

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
        "asi_constraint_extractor",
        "autoreason",
        "belief",
        "claim_gate",
        "codeintel",
        "ddtree",
        "delivery_gate",
        "drone",
        "formal_report",
        "hyper",
        "judge_panel",
        "lancedb",
        "memory",
        "mempalace_gate",
        "nightshift",
        "research",
        "semantic_searcher",
        "swarm",
        "swarm_quiet_moment",
        "ultra_review",
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
