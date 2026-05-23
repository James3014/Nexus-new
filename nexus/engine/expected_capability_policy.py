from __future__ import annotations

import re
from typing import Any


EXPECTED_EXECUTOR_CAPABILITIES = frozenset(
    {
        "autoreason",
        "ddtree",
        "drone",
        "nightshift",
        "swarm",
        "ultra_review",
    }
)
EXPECTED_CANDIDATE_FACTORY_CAPABILITIES = frozenset({"autoreason", "ddtree"})
GATE_ONLY_SUPERVISED_CAPABILITIES = frozenset(
    {
        "artifact_gate",
        "belief",
        "claim_gate",
        "delivery_gate",
        "mempalace_gate",
    }
)
PREFLIGHT_SUPERVISED_CAPABILITIES = frozenset({"codeintel", "memory"})
GATE_ONLY_RECEIPT_LITE_LANES = frozenset(
    {
        "feature_reflex",
        "governance_hardened",
        "governance_hardened_capped",
        "hidden_bugfix_supervised",
        "trust_supervised_scope_only",
    }
)
ROUTE_ORACLE_RECEIPT_LITE_CAPABILITIES = frozenset({"swarm", "ultra_review"})
DETERMINISTIC_ROUTE_ORACLE_RECEIPT_LITE_CAPABILITIES = frozenset(
    {
        "autoreason",
        "bdd_acceptance_skill",
        "ddtree",
        "drone",
        "lancedb",
        "nightshift",
        "research",
        "semantic_failure_sensor",
        "semantic_searcher",
        "swarm_quiet_moment",
    }
)


def expected_capability_executor_flags(expected_capabilities: Any) -> dict[str, bool]:
    expected = normalize_expected_capabilities(expected_capabilities)
    return {
        "enable_autoreason_executor": "autoreason" in expected,
        "enable_ddtree_executor": "ddtree" in expected,
        "enable_ultra_review_dry_gate": "ultra_review" in expected,
    }


def protect_expected_capability_controls(
    route_cost_controls: dict[str, Any] | None,
    expected_capabilities: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    controls = dict(route_cost_controls or {})
    expected = normalize_expected_capabilities(expected_capabilities)
    gate_only_receipt_lite = bool(
        expected
        and expected <= GATE_ONLY_SUPERVISED_CAPABILITIES
        and controls.get("route_lane") in GATE_ONLY_RECEIPT_LITE_LANES
        and controls.get("context_mode") == "compact"
        and int(controls.get("max_rounds", 0) or 0) == 1
        and controls.get("disable_research") is True
    )
    if gate_only_receipt_lite:
        controls["gate_only_receipt_lite"] = True
        controls["supervised_bare_first"] = True
        controls["allow_medium_risk_supervised_bare_first"] = True
        controls["allow_pre_model_deterministic_rescue"] = True
    route_oracle_receipt_lite = bool(
        expected
        and expected <= (ROUTE_ORACLE_RECEIPT_LITE_CAPABILITIES | DETERMINISTIC_ROUTE_ORACLE_RECEIPT_LITE_CAPABILITIES)
        and controls.get("route_lane")
        in (
            GATE_ONLY_RECEIPT_LITE_LANES
            | {"context_sync_capped", "feature_reflex", "hidden_lite", "memory_contract_compact"}
        )
        and controls.get("context_mode") == "compact"
        and int(controls.get("max_rounds", 0) or 0) == 1
        and controls.get("disable_research") is True
    )
    if route_oracle_receipt_lite:
        controls["route_oracle_receipt_lite"] = True
        controls["allow_pre_model_deterministic_rescue"] = True
    belief_receipt_lite = bool(
        expected == {"belief"}
        and controls.get("route_lane") == "belief_budget_hardened_capped"
        and controls.get("context_mode") == "compact"
        and int(controls.get("max_rounds", 0) or 0) == 1
        and controls.get("disable_research") is True
    )
    if belief_receipt_lite:
        controls["belief_receipt_lite"] = True
        controls["allow_pre_model_deterministic_rescue"] = True
    hyper_receipt_lite = bool(
        expected == {"hyper", "delivery_gate"}
        and controls.get("route_lane") == "repair_capped"
        and controls.get("context_mode") == "compact"
        and int(controls.get("max_rounds", 0) or 0) == 1
        and controls.get("disable_research") is True
    )
    if hyper_receipt_lite:
        controls["hyper_receipt_lite"] = True
        controls["allow_pre_model_deterministic_rescue"] = True
    if (
        "swarm" in expected
        and controls.get("route_lane") in GATE_ONLY_RECEIPT_LITE_LANES
        and controls.get("context_mode") == "compact"
        and int(controls.get("max_rounds", 0) or 0) == 1
        and controls.get("disable_research") is True
    ):
        controls["swarm_receipt_executor"] = True
    preflight_supervised = bool(
        controls.get("route_lane") in (GATE_ONLY_RECEIPT_LITE_LANES | {"context_sync_capped", "memory_contract_compact"})
        and expected
        and expected - GATE_ONLY_SUPERVISED_CAPABILITIES <= PREFLIGHT_SUPERVISED_CAPABILITIES
    )
    if preflight_supervised:
        controls["preflight_receipt_lite"] = True
        controls["allow_pre_model_deterministic_rescue"] = True
    receipt_lite_baseline = (
        ROUTE_ORACLE_RECEIPT_LITE_CAPABILITIES | DETERMINISTIC_ROUTE_ORACLE_RECEIPT_LITE_CAPABILITIES
        if route_oracle_receipt_lite
        else frozenset()
    )
    supervised_baseline = (
        GATE_ONLY_SUPERVISED_CAPABILITIES
        | receipt_lite_baseline
        | (PREFLIGHT_SUPERVISED_CAPABILITIES if preflight_supervised else frozenset())
    )
    protected = sorted(expected - supervised_baseline)
    if not protected:
        return controls, {}

    overrides: dict[str, Any] = {"protected_expected_capabilities": protected}

    if expected & EXPECTED_CANDIDATE_FACTORY_CAPABILITIES:
        candidate_cap = _positive_int_or_zero(controls.get("candidate_cap"))
        if "ddtree" in expected and candidate_cap < 3:
            overrides["candidate_cap"] = controls.pop("candidate_cap", None)
            controls["candidate_cap"] = 3
        if (
            "ddtree" in expected
            and controls.get("disable_research") is True
            and controls.get("context_mode") == "compact"
        ):
            controls["ddtree_mixed_candidate_pool"] = True
        if (
            "autoreason" in expected
            and controls.get("disable_research") is True
            and controls.get("context_mode") == "compact"
        ):
            if candidate_cap < 2:
                overrides["candidate_cap"] = controls.pop("candidate_cap", None)
            controls["autoreason_mixed_candidate_pool"] = True
        elif "ddtree" not in expected and candidate_cap < 2:
            overrides["candidate_cap"] = controls.pop("candidate_cap", None)
        if controls.get("lite_route") is True:
            overrides["lite_route"] = True
            controls["lite_route"] = False

    if expected - supervised_baseline and controls.get("supervised_bare_first") is True:
        overrides["supervised_bare_first"] = True
        controls["supervised_bare_first"] = False

    if "research" in expected and controls.get("disable_research") is True:
        overrides["disable_research"] = True
        controls["disable_research"] = False

    if controls.get("skip_llm_baseline") is True and not (
        controls.get("route_oracle_receipt_lite") is True
        or controls.get("belief_receipt_lite") is True
        or controls.get("gate_only_receipt_lite") is True
        or controls.get("hyper_receipt_lite") is True
        or controls.get("preflight_receipt_lite") is True
    ):
        overrides["skip_llm_baseline"] = True
        controls.pop("skip_llm_baseline", None)
        controls["require_llm_baseline"] = True

    if len(overrides) > 1:
        controls["expected_capability_protection"] = protected
        return controls, overrides
    return controls, {}


def normalize_expected_capabilities(value: Any) -> set[str]:
    if value in (None, "", False):
        return set()
    items: list[Any]
    if isinstance(value, str):
        items = re.split(r"[,\s]+", value)
    elif isinstance(value, list | tuple | set | frozenset):
        items = list(value)
    else:
        items = [value]
    normalized: set[str] = set()
    for item in items:
        text = str(item).strip().lower().replace("-", "_").replace(" ", "_")
        if text:
            normalized.add(text)
    return normalized


def _positive_int_or_zero(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return parsed if parsed >= 1 else 0
