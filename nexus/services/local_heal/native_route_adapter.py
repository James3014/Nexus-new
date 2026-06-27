"""B1-A: Native Route Adapter — Compact route decision for local_heal."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nexus.services.local_heal.role_contract import ROLE_CONTRACT


EXPLICIT_ROUTE_PROFILE = "qwen_3b_judge_plus_qwen_7b_plus_deepseek_6_7b"
EXPLICIT_ROUTE_ROLES = {
    "judge": {
        "allowed": ["evidence_ranking", "gate_review"],
        "forbidden": ["patch_generation"],
    },
    "proposer": {
        "allowed": ["candidate_proposal", "localized_planning"],
        "forbidden": ["patch_generation", "broad_rewrite"],
    },
    "secondary_proposer": {
        "allowed": ["secondary_candidate_proposal", "narrow_fallback_proposal"],
        "forbidden": ["patch_generation", "broad_rewrite"],
    },
}

ROUTE_RULES = {
    "preflight": {
        "3b": {"allowed": ["advisory_classification"], "forbidden": ["patch_generation"]},
        "7b": {"allowed": ["narrow_candidate_generation", "abstain"], "forbidden": ["broad_rewrite", "source_anchor_generation"]},
        "12b": {"allowed": ["semantic_fallback", "narrow_candidate_generation", "abstain"], "forbidden": ["env_blocker_case", "anchor_invalid_case"]},
    },
    "context_discovery": {
        "3b": {"allowed": ["read_evidence_packet"], "forbidden": ["codeintel_direct", "research_direct"]},
        "7b": {"allowed": ["read_evidence_packet", "narrow_candidate_generation"], "forbidden": ["broad_context_expansion"]},
        "12b": {"allowed": ["read_evidence_packet", "semantic_fallback"], "forbidden": ["broad_context_expansion"]},
    },
    "candidate_generation": {
        "3b": {"allowed": [], "forbidden": ["patch_generation"]},
        "7b": {"allowed": ["narrow_candidate_generation", "abstain"], "forbidden": ["broad_rewrite"]},
        "12b": {"allowed": ["semantic_fallback", "narrow_candidate_generation"], "forbidden": ["env_blocker_case"]},
    },
    "validation": {
        "3b": {"allowed": [], "forbidden": ["verifier_override"]},
        "7b": {"allowed": [], "forbidden": ["verifier_override", "self_rating"]},
        "12b": {"allowed": [], "forbidden": ["verifier_override", "self_rating"]},
    },
    "delivery_classification": {
        "3b": {"allowed": [], "forbidden": ["success_claim"]},
        "7b": {"allowed": [], "forbidden": ["success_claim"]},
        "12b": {"allowed": [], "forbidden": ["success_claim"]},
    },
}


@dataclass
class RouteRequest:
    task_id: str
    repo_path: str
    base_commit: str
    issue_summary: str
    failing_test_summary: str
    selected_anchor: str
    model_role_requested: str
    resource_profile: str
    phase: str
    route_profile: str = ""
    route_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RouteDecision:
    route_id: str
    route_allowed: bool
    route_profile: str
    explicit_route: bool
    allowed_capabilities: list[str]
    forbidden_capabilities: list[str]
    model_role: str
    context_budget: str
    escalation_policy: str
    gate_reasons: list[str]
    authority_trace: list[str]
    route_metadata: dict[str, Any] = field(default_factory=dict)


class NativeRouteAdapter:
    """Compact route adapter binding local_heal to Nexus routing/gating logic."""

    def decide(self, request: RouteRequest) -> RouteDecision:
        route_profile = request.route_profile or str(request.route_metadata.get("route_profile", ""))
        if not route_profile:
            return self._decide_legacy(request)

        is_manual_only = bool(request.route_metadata.get("manual_only_experimental"))
        is_manual_invocation_only = bool(request.route_metadata.get("manual_invocation_only"))
        has_local_patterns = self._has_local_patterns(request)
        explicit_route = (
            route_profile == EXPLICIT_ROUTE_PROFILE
            and is_manual_only
            and is_manual_invocation_only
            and has_local_patterns
        )

        route_id = f"route_{request.task_id}_{route_profile or request.phase}"
        gate_reasons: list[str] = []
        authority_trace = [
            f"NativeRouteAdapter:phase={request.phase}:role={request.model_role_requested}",
            f"NativeRouteAdapter:route_profile={route_profile or 'auto'}:explicit={explicit_route}",
        ]

        if not route_profile:
            gate_reasons.append("route_requires_explicit_profile")
        if route_profile and route_profile != EXPLICIT_ROUTE_PROFILE:
            gate_reasons.append("route_profile_not_supported")
        if not is_manual_only:
            gate_reasons.append("manual_only_experimental_missing")
        if not is_manual_invocation_only:
            gate_reasons.append("manual_invocation_only_missing")
        if not has_local_patterns:
            gate_reasons.append("local_pattern_missing")

        role_rules = EXPLICIT_ROUTE_ROLES.get(request.model_role_requested, {}) if explicit_route else {}
        allowed = list(role_rules.get("allowed", []))
        forbidden = list(role_rules.get("forbidden", []))

        if explicit_route and request.model_role_requested not in ROLE_CONTRACT:
            gate_reasons.append("route_role_not_contracted")

        if explicit_route and request.model_role_requested == "judge":
            context_budget = "bounded_evidence_packet_only"
        elif explicit_route and request.model_role_requested == "proposer":
            context_budget = "bounded_candidate_only"
        elif explicit_route and request.model_role_requested == "secondary_proposer":
            context_budget = "secondary_proposal_only"
        else:
            context_budget = "manual_route_blocked"

        escalation = "manual_only_opt_in"
        if request.resource_profile == "14b_cpu_only":
            forbidden.append("14b_cpu_forbidden")
            gate_reasons.append("resource_guard_blocked")
            escalation = "blocked_cpu_unsafe"
        elif request.resource_profile == "cloud_without_approval":
            forbidden.append("cloud_requires_owner_approval")
            gate_reasons.append("cloud_approval_required")
            escalation = "blocked_no_approval"

        resource_blocked = request.resource_profile in {"14b_cpu_only", "cloud_without_approval"}
        route_allowed = explicit_route and not resource_blocked
        if not route_allowed and explicit_route:
            gate_reasons.append("route_explicitly_blocked")
        if not explicit_route:
            allowed = []
            forbidden.extend(["route_not_explicitly_opted_in"])

        return RouteDecision(
            route_id=route_id,
            route_allowed=route_allowed,
            route_profile=route_profile or "",
            explicit_route=explicit_route,
            allowed_capabilities=allowed,
            forbidden_capabilities=forbidden,
            model_role=request.model_role_requested,
            context_budget=context_budget,
            escalation_policy=escalation,
            gate_reasons=gate_reasons,
            authority_trace=authority_trace,
            route_metadata={
                "manual_only_experimental": is_manual_only,
                "manual_invocation_only": is_manual_invocation_only,
                "has_local_patterns": has_local_patterns,
            },
        )

    def _has_local_patterns(self, request: RouteRequest) -> bool:
        haystack = " \n".join(
            part for part in (
                request.issue_summary,
                request.failing_test_summary,
                request.selected_anchor,
                request.repo_path,
            )
            if part
        ).lower()
        return any(
            token in haystack
            for token in (
                ".py",
                "def ",
                "class ",
                "traceback",
                "assertionerror",
                "pytest",
                "test_",
                "local_heal",
            )
        )

    def _decide_legacy(self, request: RouteRequest) -> RouteDecision:
        route_id = f"route_{request.task_id}_{request.phase}"
        phase_rules = ROUTE_RULES.get(request.phase, {})
        role_rules = phase_rules.get(request.model_role_requested, {})

        allowed = list(role_rules.get("allowed", []))
        forbidden = list(role_rules.get("forbidden", []))

        anchor_valid = bool(request.selected_anchor and request.selected_anchor.strip())
        if not anchor_valid and request.phase in ("candidate_generation", "validation"):
            forbidden.append("anchor_invalid_blocks_generation")
            allowed = []

        escalation = "allow_if_resource_safe"
        if request.resource_profile == "14b_cpu_only":
            forbidden.append("14b_cpu_forbidden")
            escalation = "blocked_cpu_unsafe"
        elif request.resource_profile == "cloud_without_approval":
            forbidden.append("cloud_requires_owner_approval")
            escalation = "blocked_no_approval"

        route_allowed = bool(allowed) and "anchor_invalid_blocks_generation" not in forbidden
        gate_reasons = []
        authority_trace = [f"NativeRouteAdapter:phase={request.phase}:role={request.model_role_requested}"]

        if not anchor_valid:
            gate_reasons.append("anchor_invalid")
        if "14b_cpu_forbidden" in forbidden:
            gate_reasons.append("resource_guard_blocked")
        if "cloud_requires_owner_approval" in forbidden:
            gate_reasons.append("cloud_approval_required")

        context_budget = "bounded_evidence_packet_only"
        if request.model_role_requested == "3b":
            context_budget = "minimal_advisory_only"

        return RouteDecision(
            route_id=route_id,
            route_allowed=route_allowed,
            route_profile="",
            explicit_route=False,
            allowed_capabilities=allowed,
            forbidden_capabilities=forbidden,
            model_role=request.model_role_requested,
            context_budget=context_budget,
            escalation_policy=escalation,
            gate_reasons=gate_reasons,
            authority_trace=authority_trace,
            route_metadata={},
        )
