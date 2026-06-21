"""B1-A: Native Route Adapter — Compact route decision for local_heal."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


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


@dataclass
class RouteDecision:
    route_id: str
    route_allowed: bool
    allowed_capabilities: list[str]
    forbidden_capabilities: list[str]
    model_role: str
    context_budget: str
    escalation_policy: str
    gate_reasons: list[str]
    authority_trace: list[str]


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


class NativeRouteAdapter:
    """Compact route adapter binding local_heal to Nexus routing/gating logic."""

    def decide(self, request: RouteRequest) -> RouteDecision:
        route_id = f"route_{request.task_id}_{request.phase}"
        phase_rules = ROUTE_RULES.get(request.phase, {})
        role_rules = phase_rules.get(request.model_role_requested, {})

        allowed = role_rules.get("allowed", [])
        forbidden = role_rules.get("forbidden", [])

        # Validate anchor
        anchor_valid = bool(request.selected_anchor and request.selected_anchor.strip())
        if not anchor_valid and request.phase in ("candidate_generation", "validation"):
            forbidden.append("anchor_invalid_blocks_generation")
            allowed = []

        # Resource policy
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
            allowed_capabilities=allowed,
            forbidden_capabilities=forbidden,
            model_role=request.model_role_requested,
            context_budget=context_budget,
            escalation_policy=escalation,
            gate_reasons=gate_reasons,
            authority_trace=authority_trace,
        )
