from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
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
from nexus.services.local_heal.capability_runtime_policy import build_local_heal_runtime_policy
from nexus.services.local_heal.local_model_provider import (
    LocalModelProvider,
    InertLocalModelProvider,
    InjectedLocalModelProvider,
    OllamaLocalModelProvider,
)
from nexus.services.local_heal.local_model_advisory_adapter import (
    LocalModelAdvisoryAdapter,
    LocalModelAdvisoryRequest,
)
from nexus.services.local_heal.local_model_candidate_adapter import (
    LocalModelCandidateAdapter,
    LocalModelCandidateRequest,
)
from nexus.services.local_heal.local_guard_fail_closed import (
    LocalGuardInput,
    run_local_guard_fail_closed,
)


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


def build_local_model_provider_from_env(
    env: Mapping[str, str],
    controls: Mapping[str, Any],
    injected_fn_key: str,
) -> LocalModelProvider:
    call_allowed = env.get("NEXUS_LOCAL_MODEL_CALL_ALLOWED") == "1"
    if not call_allowed:
        return InertLocalModelProvider()
        
    injected_fn = controls.get(injected_fn_key)
    if injected_fn is not None:
        return InjectedLocalModelProvider(injected_fn)
        
    provider_type = env.get("NEXUS_LOCAL_MODEL_PROVIDER", "").lower()
    model_name = env.get("NEXUS_LOCAL_MODEL_NAME", "").strip()
    
    if provider_type == "ollama" and model_name:
        return OllamaLocalModelProvider()
        
    return InertLocalModelProvider()


class LocalHealCapabilityAdapter:
    @staticmethod
    def run(request: LocalHealCapabilityRequest) -> LocalHealCapabilityResponse:
        controls = request.executor_controls
        enable_local_heal = bool(controls.get("enable_local_heal", False))
        local_heal_mode = controls.get("local_heal_mode", "disabled")
        
        policy = build_local_heal_runtime_policy(os.environ, controls)
        
        advisory_enabled = os.environ.get("NEXUS_LOCAL_MODEL_ADVISORY_ENABLE") == "1"
        candidate_enabled = os.environ.get("NEXUS_LOCAL_MODEL_CANDIDATE_ENABLE") == "1"
        call_allowed = os.environ.get("NEXUS_LOCAL_MODEL_CALL_ALLOWED") == "1"
        
        if candidate_enabled:
            cand_blockers = []
            if not call_allowed:
                cand_blockers.append("model_call_not_allowed")
                
            provider = build_local_model_provider_from_env(
                os.environ, controls, "candidate_generate_fn"
            )
            
            cand_req = LocalModelCandidateRequest(
                task_id=request.task_id,
                problem_statement=request.problem_statement,
                evidence_refs=request.evidence_refs,
                prompt="suggest candidate change",
            )
            cand_resp = LocalModelCandidateAdapter.run(cand_req, provider=provider)
            
            all_blockers = sorted(set(list(cand_resp.blockers) + cand_blockers))
            fallback_block_reason = ";".join(all_blockers)
            
            cand_metadata = {
                "candidate_id": cand_resp.candidate_id,
                "candidate_output_isolated": cand_resp.candidate_output_isolated,
                "selected_candidate_hash": cand_resp.selected_candidate_hash,
                "applied_patch_hash": cand_resp.applied_patch_hash,
                "verifier_result": cand_resp.verifier_result,
                "provider_invoked": cand_resp.candidate_invoked,
                "provider_error": cand_resp.blockers[2] if len(cand_resp.blockers) > 2 else "",
                "model_name": os.environ.get("NEXUS_LOCAL_MODEL_NAME", ""),
            }
            
            payload = build_hybrid_route_decision(
                route_mode=RouteMode.LOCAL_ONLY_BLOCKED,
                public_claim_allowed=False,
                production_ready=False,
                adapter_output_is_route_truth=False,
                route_truth_source="CapabilityPlanner",
                behavior_changed=False,
                authority=Authority.TRACE_ONLY,
                local_model_called=cand_resp.local_model_called,
                candidate_output_isolated=cand_resp.candidate_output_isolated,
                selected_candidate_hash=cand_resp.selected_candidate_hash,
                applied_patch_hash=cand_resp.applied_patch_hash,
                selected_candidate_hash_matches_applied=cand_resp.selected_candidate_hash_matches_applied,
                verifier_result=VerifierResult.NOT_RUN,
                evidence_refs=request.evidence_refs,
                fallback_block_reason=fallback_block_reason,
                metadata=cand_metadata,
            )
            decision = hybrid_route_decision_from_payload(payload)
            invoked = True
            
        elif advisory_enabled:
            advis_blockers = []
            if not call_allowed:
                advis_blockers.append("model_call_not_allowed")
                
            provider = build_local_model_provider_from_env(
                os.environ, controls, "advisory_generate_fn"
            )
            
            advis_req = LocalModelAdvisoryRequest(
                task_id=request.task_id,
                problem_statement=request.problem_statement,
                evidence_refs=request.evidence_refs,
            )
            advis_resp = LocalModelAdvisoryAdapter.run(advis_req, provider=provider)
            
            text_hash = hashlib.sha256(advis_resp.advisory_text.encode("utf-8")).hexdigest()
            text_preview = advis_resp.advisory_text[:100]
            
            all_blockers = sorted(set(list(advis_resp.advisory_blockers) + advis_blockers))
            fallback_block_reason = ";".join(all_blockers)
            
            advis_metadata = {
                "advisory_invoked": advis_resp.advisory_invoked,
                "local_model_called": advis_resp.local_model_called,
                "advisory_blockers": list(advis_resp.advisory_blockers),
                "advisory_text_hash": text_hash,
                "advisory_text_preview": text_preview,
                "provider_invoked": advis_resp.advisory_invoked,
                "provider_error": all_blockers[0] if all_blockers else "",
                "model_name": os.environ.get("NEXUS_LOCAL_MODEL_NAME", ""),
            }
            
            payload = build_hybrid_route_decision(
                route_mode=RouteMode.CLOUD_FIRST_LOCAL_GUARD_ADVISORY,
                public_claim_allowed=False,
                production_ready=False,
                adapter_output_is_route_truth=False,
                route_truth_source="CapabilityPlanner",
                behavior_changed=False,
                authority=Authority.ADVISORY_ONLY,
                local_model_called=advis_resp.local_model_called,
                verifier_result=VerifierResult.NOT_RUN,
                evidence_refs=request.evidence_refs,
                fallback_block_reason=fallback_block_reason,
                metadata=advis_metadata,
            )
            decision = hybrid_route_decision_from_payload(payload)
            invoked = True
            
        elif not enable_local_heal or (local_heal_mode == "disabled" and not policy.enable_pipeline):
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
            
        elif enable_local_heal and (local_heal_mode == "shadow_only" or policy.enable_pipeline):
            blockers = []
            if not request.evidence_refs:
                blockers.append("missing_evidence_refs")
            
            if local_heal_mode == "shadow_only":
                blockers.append("shadow_only_no_runtime")
                
            if not policy.mutation_allowed:
                blockers.append("mutation_not_allowed")
                
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
            
        if os.environ.get("NEXUS_LOCAL_GUARD_FAIL_CLOSED_ENABLE") == "1":
            vr_val = payload.get("verifier_result")
            vr_str = vr_val.value if hasattr(vr_val, "value") else str(vr_val) if vr_val else "not_run"
            
            vr_str_in = controls.get("verifier_result", vr_str)
            sel_hash_in = controls.get("selected_candidate_hash", payload.get("selected_candidate_hash", ""))
            app_hash_in = controls.get("applied_patch_hash", payload.get("applied_patch_hash", ""))
            rts_in = controls.get("route_truth_source", payload.get("route_truth_source", "CapabilityPlanner"))
            
            guard_input = LocalGuardInput(
                task_id=request.task_id,
                route_payload=payload,
                evidence_refs=payload.get("evidence_refs", ()),
                verifier_result=vr_str_in,
                selected_candidate_hash=sel_hash_in,
                applied_patch_hash=app_hash_in,
                route_truth_source=rts_in,
            )
            
            decision_guard = run_local_guard_fail_closed(guard_input)
            if decision_guard.guard_blocked:
                old_blockers = [b for b in payload.get("fallback_block_reason", "").split(";") if b]
                all_blockers = sorted(set(list(decision_guard.blockers) + old_blockers))
                fallback_block_reason = ";".join(all_blockers)
                
                payload = build_hybrid_route_decision(
                    route_mode=RouteMode.CLOUD_FIRST_LOCAL_GUARD_FAIL_CLOSED,
                    public_claim_allowed=False,
                    production_ready=False,
                    adapter_output_is_route_truth=False,
                    route_truth_source="CapabilityPlanner",
                    behavior_changed=False,
                    authority=Authority.FAIL_CLOSED,
                    local_model_called=payload.get("local_model_called", False),
                    verifier_result=vr_val,
                    evidence_refs=payload.get("evidence_refs", ()),
                    fallback_block_reason=fallback_block_reason,
                    metadata=payload.get("metadata", {}),
                )
                decision = hybrid_route_decision_from_payload(payload)
                
        capability_payload = capability_payload_from_hybrid_route(decision)
        capability_payload["adapter_invoked"] = invoked
        
        return LocalHealCapabilityResponse(
            task_id=request.task_id,
            invoked=invoked,
            hybrid_route=decision,
            capability_payload=capability_payload,
        )
