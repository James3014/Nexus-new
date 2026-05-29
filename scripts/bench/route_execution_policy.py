from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


DETERMINISTIC_PRE_RESCUE_LANES = frozenset(
    {
        "context_sync_capped",
        "feature_reflex",
        "governance_hardened",
        "governance_hardened_capped",
        "memory_contract_compact",
        "belief_budget_hardened_capped",
        "hidden_bugfix_supervised",
        "hidden_lite",
        "repair_capped",
        "trust_supervised_scope_only",
    }
)

RECEIPT_LITE_FLAGS = (
    "route_oracle_receipt_lite",
    "belief_receipt_lite",
    "gate_only_receipt_lite",
    "hyper_receipt_lite",
    "preflight_receipt_lite",
)

from nexus.core.lane_policy_defaults import LANE_POLICY_DEFAULTS

_REASON_CODE_MAPPING = {
    "allow_pre_model_deterministic_rescue": "lane_default_pre_model_rescue",
    "skip_llm_baseline": "lane_default_skip_baseline",
    "supervised_bare_first": "lane_default_supervised_bare_first",
}


@dataclass(frozen=True)
class RouteExecutionPolicy:
    supervised_bare_first_allowed: bool
    deterministic_pre_rescue_allowed: bool
    pre_model_deterministic_rescue_allowed: bool
    baseline_fast_path_preferred: bool
    reason_codes: tuple[str, ...]
    supervised_bare_first_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "supervised_bare_first_allowed": self.supervised_bare_first_allowed,
            "deterministic_pre_rescue_allowed": self.deterministic_pre_rescue_allowed,
            "pre_model_deterministic_rescue_allowed": self.pre_model_deterministic_rescue_allowed,
            "baseline_fast_path_preferred": self.baseline_fast_path_preferred,
            "supervised_bare_first_reason": self.supervised_bare_first_reason,
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True)
class ModelParticipationRescuePolicy:
    route_cost_controls: dict[str, Any]
    route_cost_policy_overrides: dict[str, Any]
    require_model_participation_for_run: bool
    allow_cost_efficiency_pre_model_rescue: bool


def apply_model_participation_rescue_policy(
    route_cost_controls: Mapping[str, Any],
    route_cost_policy_overrides: Mapping[str, Any],
    *,
    llm_enabled: bool,
    require_model_participation_env: bool,
    disable_deterministic_rescue_env: bool,
    allow_cost_efficiency_pre_model_rescue_env: bool,
) -> ModelParticipationRescuePolicy:
    controls = dict(route_cost_controls)
    overrides = dict(route_cost_policy_overrides)
    require_model_participation_for_run = bool(llm_enabled and require_model_participation_env)
    allow_cost_efficiency_pre_model_rescue = bool(allow_cost_efficiency_pre_model_rescue_env)

    if llm_enabled and disable_deterministic_rescue_env:
        controls["disable_deterministic_rescue"] = True
        overrides["disable_deterministic_rescue"] = True
        controls["allow_pre_model_deterministic_rescue"] = False

    if require_model_participation_for_run:
        if controls.get("allow_pre_model_deterministic_rescue") is True:
            overrides["allow_pre_model_deterministic_rescue"] = True
        if not allow_cost_efficiency_pre_model_rescue:
            controls["allow_pre_model_deterministic_rescue"] = False
        else:
            controls["cost_efficiency_pre_model_rescue_profile"] = True
        controls["require_model_participation"] = True

    return ModelParticipationRescuePolicy(
        route_cost_controls=controls,
        route_cost_policy_overrides=overrides,
        require_model_participation_for_run=require_model_participation_for_run,
        allow_cost_efficiency_pre_model_rescue=allow_cost_efficiency_pre_model_rescue,
    )


def prefer_baseline_fast_path(route_cost_controls: Mapping[str, Any]) -> bool:
    if route_cost_controls.get("expected_capability_protection"):
        return False
    return bool(
        route_cost_controls.get("lite_route") is True
        and route_cost_controls.get("route_lane") == "hidden_lite"
        and route_cost_controls.get("context_mode") == "compact"
        and int(route_cost_controls.get("max_rounds", 0) or 0) == 1
    )


def allow_deterministic_pre_rescue(route_cost_controls: Mapping[str, Any]) -> bool:
    if route_cost_controls.get("disable_deterministic_rescue") is True:
        return False
    if prefer_baseline_fast_path(route_cost_controls):
        return True
    max_rounds = int(route_cost_controls.get("max_rounds", 0) or 0)
    if route_cost_controls.get("route_lane") == "memory_contract_compact":
        max_rounds_allowed = max_rounds <= 2
    else:
        max_rounds_allowed = max_rounds == 1
    return bool(
        route_cost_controls.get("route_lane") in DETERMINISTIC_PRE_RESCUE_LANES
        and route_cost_controls.get("context_mode") == "compact"
        and max_rounds_allowed
        and route_cost_controls.get("disable_research") is True
    )


def allow_pre_model_deterministic_rescue(route_cost_controls: Mapping[str, Any]) -> bool:
    receipt_lite = any(route_cost_controls.get(flag) is True for flag in RECEIPT_LITE_FLAGS)
    return bool(
        route_cost_controls.get("allow_pre_model_deterministic_rescue") is True
        and route_cost_controls.get("route_lane") in DETERMINISTIC_PRE_RESCUE_LANES
        and allow_deterministic_pre_rescue(route_cost_controls)
        and (receipt_lite or not route_cost_controls.get("expected_capability_protection"))
    )


def supervised_bare_first_reason(route_cost_controls: Mapping[str, Any]) -> str:
    if route_cost_controls.get("supervised_bare_first") is True:
        return "policy_explicit"
    if prefer_baseline_fast_path(route_cost_controls):
        return "hidden_lite_ghost_governance"
    return ""


def decide_route_execution_policy(
    *,
    route_cost_controls: Mapping[str, Any],
    llm_enabled: bool,
    hidden_verifier_required: bool,
    eligibility_class: str,
    capability_activation_contract: str = "",
    local_reflex_risk_level: str,
    local_reflex_bare_sufficiency: str,
) -> RouteExecutionPolicy:
    reasons: list[str] = []
    baseline_fast_path = prefer_baseline_fast_path(route_cost_controls)
    deterministic_pre_rescue = allow_deterministic_pre_rescue(route_cost_controls)
    pre_model_rescue = allow_pre_model_deterministic_rescue(route_cost_controls)
    protection_present = bool(route_cost_controls.get("expected_capability_protection"))
    receipt_lite = any(route_cost_controls.get(flag) is True for flag in RECEIPT_LITE_FLAGS)
    protected_cost_capped_pre_rescue = bool(
        protection_present
        and capability_activation_contract == "cost_capped"
        and route_cost_controls.get("allow_pre_model_deterministic_rescue") is True
        and route_cost_controls.get("route_lane") in DETERMINISTIC_PRE_RESCUE_LANES
        and deterministic_pre_rescue
        and local_reflex_risk_level == "low"
        and local_reflex_bare_sufficiency == "high"
    )
    if protected_cost_capped_pre_rescue:
        pre_model_rescue = True
        reasons.append("cost_capped_capability_allows_verified_pre_model_rescue")
    if not llm_enabled:
        reasons.append("llm_disabled")
    if not hidden_verifier_required:
        reasons.append("hidden_verifier_required")
    if eligibility_class == "model_required" and pre_model_rescue and not receipt_lite:
        pre_model_rescue = False
        reasons.append("model_required_blocks_pre_model_rescue")
    if eligibility_class == "model_required" and pre_model_rescue and receipt_lite:
        reasons.append("model_required_receipt_lite_allows_pre_model_rescue")
    if protection_present and not protected_cost_capped_pre_rescue and not receipt_lite:
        reasons.append("expected_capability_protection")
    if route_cost_controls.get("allow_pre_model_deterministic_rescue") is True and not pre_model_rescue:
        reasons.append("pre_model_rescue_configured_but_blocked")

    supervised_allowed = bool(
        llm_enabled
        and (route_cost_controls.get("supervised_bare_first") is True or baseline_fast_path)
        and hidden_verifier_required
        and (
            (local_reflex_risk_level == "low" and local_reflex_bare_sufficiency == "high")
            or (
                local_reflex_risk_level == "medium"
                and local_reflex_bare_sufficiency == "medium"
                and route_cost_controls.get("allow_medium_risk_supervised_bare_first") is True
            )
            or route_cost_controls.get("allow_high_risk_supervised_bare_first") is True
        )
    )
    if not supervised_allowed and (route_cost_controls.get("supervised_bare_first") is True or baseline_fast_path):
        reasons.append("supervised_bare_first_blocked")

    # Annotate lane-default reason codes so route evidence reflects the origin of each control.
    lane = str(route_cost_controls.get("route_lane") or "")
    lane_defaults = LANE_POLICY_DEFAULTS.get(lane, {})
    for control_key, default_val in lane_defaults.items():
        if default_val is True and route_cost_controls.get(control_key) is True:
            reason_code = _REASON_CODE_MAPPING.get(control_key)
            if reason_code:
                reasons.append(reason_code)

    return RouteExecutionPolicy(
        supervised_bare_first_allowed=supervised_allowed,
        deterministic_pre_rescue_allowed=deterministic_pre_rescue,
        pre_model_deterministic_rescue_allowed=bool(llm_enabled and pre_model_rescue),
        baseline_fast_path_preferred=baseline_fast_path,
        supervised_bare_first_reason=supervised_bare_first_reason(route_cost_controls),
        reason_codes=tuple(sorted(set(reasons))),
    )
