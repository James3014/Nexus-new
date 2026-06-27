from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from nexus.contracts.hybrid_route import (
    HybridRouteDecision,
    RouteMode,
    VerifierResult,
    Authority,
    build_hybrid_route_decision,
    hybrid_route_decision_from_payload,
)
from nexus.services.local_heal.hybrid_route_bridge import capability_payload_from_hybrid_route


@dataclass(frozen=True)
class LocalHealCapabilityRequest:
    task_id: str
    problem_statement: str
    evidence_refs: tuple[str, ...]
    executor_controls: Mapping[str, Any]
    dry_run: bool = True


@dataclass(frozen=True)
class LocalHealCapabilityResponse:
    task_id: str
    invoked: bool
    hybrid_route: HybridRouteDecision
    capability_payload: dict[str, Any]


class LocalHealCapabilityAdapter:
    @staticmethod
    def run(request: LocalHealCapabilityRequest) -> LocalHealCapabilityResponse:
        controls = request.executor_controls
        enable_local_heal = bool(controls.get("enable_local_heal", False))
        local_heal_mode = controls.get("local_heal_mode", "disabled")
        
        if not enable_local_heal or local_heal_mode == "disabled":
            payload = build_hybrid_route_decision(
                route_mode=RouteMode.CLOUD_ASSISTED_BY_LOCAL_TRACE_ONLY,
                public_claim_allowed=False,
                production_ready=False,
                adapter_output_is_route_truth=False,
                route_truth_source="CapabilityPlanner",
                behavior_changed=False,
                authority=Authority.TRACE_ONLY,
                local_model_called=False,
                verifier_result=VerifierResult.NOT_RUN,
                evidence_refs=request.evidence_refs,
            )
            decision = hybrid_route_decision_from_payload(payload)
            invoked = False
            
        elif enable_local_heal and local_heal_mode == "shadow_only":
            blockers = ["shadow_only_no_runtime"]
            if not request.evidence_refs:
                blockers.append("missing_evidence_refs")
            
            fallback_block_reason = ";".join(sorted(blockers))
            
            payload = build_hybrid_route_decision(
                route_mode=RouteMode.LOCAL_ONLY_BLOCKED,
                public_claim_allowed=False,
                production_ready=False,
                adapter_output_is_route_truth=False,
                route_truth_source="CapabilityPlanner",
                behavior_changed=False,
                authority=Authority.TRACE_ONLY,
                local_model_called=False,
                verifier_result=VerifierResult.NOT_RUN,
                evidence_refs=request.evidence_refs,
                fallback_block_reason=fallback_block_reason,
            )
            decision = hybrid_route_decision_from_payload(payload)
            invoked = True
            
        else:
            payload = build_hybrid_route_decision(
                route_mode=RouteMode.LOCAL_ONLY_BLOCKED,
                public_claim_allowed=False,
                production_ready=False,
                adapter_output_is_route_truth=False,
                route_truth_source="CapabilityPlanner",
                behavior_changed=False,
                authority=Authority.TRACE_ONLY,
                local_model_called=False,
                verifier_result=VerifierResult.NOT_RUN,
                evidence_refs=request.evidence_refs,
                fallback_block_reason="unsupported_local_heal_mode",
            )
            decision = hybrid_route_decision_from_payload(payload)
            invoked = False
            
        capability_payload = capability_payload_from_hybrid_route(decision)
        capability_payload["adapter_invoked"] = invoked
        
        return LocalHealCapabilityResponse(
            task_id=request.task_id,
            invoked=invoked,
            hybrid_route=decision,
            capability_payload=capability_payload,
        )
