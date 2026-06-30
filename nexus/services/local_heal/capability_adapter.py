# WARNING: This module is legacy deprecated. Do NOT use it for route/planner authority decisions.
# All production routes flow strictly via CapabilityPlanner -> signal_snapshot -> downstream executors.
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
from nexus.services.local_heal.isolated_local_solve_loop import (
    IsolatedLocalSolveRequest,
    run_isolated_local_solve_loop,
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


def build_local_model_provider(
    signal_snapshot: Mapping[str, Any],
    controls: Mapping[str, Any],
    injected_fn_key: str,
) -> LocalModelProvider:
    call_allowed = bool(signal_snapshot.get("model_call_allowed", False))
    if not call_allowed:
        return InertLocalModelProvider()
        
    injected_fn = controls.get(injected_fn_key)
    if injected_fn is not None:
        return InjectedLocalModelProvider(injected_fn)
        
    provider_type = signal_snapshot.get("executor_provider", "").lower()
    model_name = signal_snapshot.get("executor_model", "").strip()
    
    if provider_type == "ollama" and model_name:
        return OllamaLocalModelProvider()
        
    return InertLocalModelProvider()


class LocalHealCapabilityAdapter:
    @staticmethod
    def run(request: LocalHealCapabilityRequest) -> LocalHealCapabilityResponse:
        controls = request.executor_controls
        
        # 1. Strictly fail closed if planner output is missing
        route_ctx = controls.get("route_context", {}) if hasattr(controls, "get") else {}
        signal_snapshot = route_ctx.get("signal_snapshot") if hasattr(route_ctx, "get") else None
        
        if not hasattr(signal_snapshot, "get") or not signal_snapshot:
            payload = build_hybrid_route_decision(
                route_mode=RouteMode.LOCAL_ONLY_BLOCKED,
                public_claim_allowed=False,
                production_ready=False,
                adapter_output_is_route_truth=False,
                route_truth_source="CapabilityPlanner",
                behavior_changed=False,
                authority=Authority.FAIL_CLOSED,
                local_model_called=False,
                verifier_result=VerifierResult.NOT_RUN,
                evidence_refs=request.evidence_refs,
                fallback_block_reason="missing_signal_snapshot",
                metadata={"error": "Missing signal_snapshot in route_context"},
            )
            decision = hybrid_route_decision_from_payload(payload)
            capability_payload = capability_payload_from_hybrid_route(decision)
            capability_payload["adapter_invoked"] = False
            return LocalHealCapabilityResponse(
                task_id=request.task_id,
                invoked=False,
                hybrid_route=decision,
                capability_payload=capability_payload,
            )
            
        enable_local_heal = bool(controls.get("enable_local_heal", False))
        local_heal_mode = controls.get("local_heal_mode", "disabled")
        
        # Required controls and blockers checks first
        candidate_enabled = bool(signal_snapshot.get("candidate_enabled", False))
        
        if candidate_enabled:
            required_keys = ["source_root", "target_file", "target_symbol", "locked_search", "verifier_command", "work_dir"]
            missing_controls = [k for k in required_keys if controls.get(k) is None]
            if not request.evidence_refs:
                missing_controls.append("evidence_refs")
                
            if missing_controls:
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
                    fallback_block_reason="missing_required_control",
                )
                decision = hybrid_route_decision_from_payload(payload)
                invoked = False
                capability_payload = capability_payload_from_hybrid_route(decision)
                capability_payload["adapter_invoked"] = False
                return LocalHealCapabilityResponse(
                    task_id=request.task_id,
                    invoked=False,
                    hybrid_route=decision,
                    capability_payload=capability_payload,
                )

        if request.dry_run:
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
                fallback_block_reason="dry_run",
                metadata={"dry_run": True},
            )
            decision = hybrid_route_decision_from_payload(payload)
            capability_payload = capability_payload_from_hybrid_route(decision)
            capability_payload["adapter_invoked"] = False
            capability_payload["dry_run_invoked"] = False
            capability_payload["metadata"] = {"dry_run": True}
            return LocalHealCapabilityResponse(
                task_id=request.task_id,
                invoked=False,
                hybrid_route=decision,
                capability_payload=capability_payload,
            )
            
        policy = build_local_heal_runtime_policy(route_ctx, controls)
        
        advisory_enabled = bool(signal_snapshot.get("advisory_enabled", False))
        candidate_enabled = bool(signal_snapshot.get("candidate_enabled", False))
        call_allowed = bool(signal_snapshot.get("model_call_allowed", False))
        isolated_solve_enabled = bool(signal_snapshot.get("isolated_solve_enabled", False))
        
        if candidate_enabled and isolated_solve_enabled:
            required_keys = ["source_root", "target_file", "target_symbol", "locked_search", "verifier_command", "work_dir"]
            missing_controls = [k for k in required_keys if controls.get(k) is None]
            if not request.evidence_refs:
                missing_controls.append("evidence_refs")
                
            if missing_controls:
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
                    fallback_block_reason="missing_required_control",
                )
                decision = hybrid_route_decision_from_payload(payload)
                invoked = False
                capability_payload = capability_payload_from_hybrid_route(decision)
            else:
                provider = build_local_model_provider(
                    signal_snapshot, controls, "candidate_generate_fn"
                )
                
                target_file = controls["target_file"]
                target_symbol = controls["target_symbol"]
                locked_search = controls["locked_search"]
                verifier_cmd = controls.get("verifier_command", [])
                
                explicit_prompt = (
                    f"You are generating a unified diff to solve a coding task.\n"
                    f"Problem: {request.problem_statement}\n"
                    f"Target File: {target_file}\n"
                    f"Target Symbol: {target_symbol}\n"
                    f"Locked Search Span (you must only modify this code block):\n"
                    f"```\n{locked_search}\n```\n\n"
                    f"Expected Verifier Goal/Verification: {verifier_cmd}\n\n"
                    f"Return only a standard unified diff wrapped in fenced ```diff block.\n"
                    f"Do not include any prose, explanation, or extra commentary.\n"
                    f"You MUST use standard header naming with a/ and b/ prefix. Example:\n"
                    f"--- a/{target_file}\n"
                    f"+++ b/{target_file}\n"
                    f"Make sure the hunk headers (e.g. @@ -L,C +L,C @@) match and only modify code within the locked search span.\n"
                )
                
                prov_req = LocalModelCandidateRequest(
                    task_id=request.task_id,
                    problem_statement=request.problem_statement,
                    evidence_refs=request.evidence_refs,
                    prompt=explicit_prompt,
                )
                prov_resp = LocalModelCandidateAdapter.run(prov_req, provider=provider)
                
                solve_req = IsolatedLocalSolveRequest(
                    task_id=request.task_id,
                    source_root=controls["source_root"],
                    problem_statement=request.problem_statement,
                    evidence_refs=request.evidence_refs,
                    model_output=prov_resp.candidate_text,
                    verifier_command=tuple(controls["verifier_command"]),
                    work_dir=controls["work_dir"],
                    local_model_called=prov_resp.local_model_called,
                    mutation_allowed=bool(signal_snapshot.get("mutation_allowed", False)),
                    verifier_allowed=bool(signal_snapshot.get("verifier_allowed", False)),
                    target_file=controls["target_file"],
                    target_symbol=controls["target_symbol"],
                    locked_search=controls["locked_search"],
                )
                solve_resp = run_isolated_local_solve_loop(solve_req)
                
                fallback_block_reason = solve_resp.hybrid_route.fallback_block_reason or ""
                verifier_status = solve_resp.capability_payload["metadata"].get("verifier_status", "not_run")
                reasons_set = set(fallback_block_reason.split(";")) if fallback_block_reason else set()
                
                should_retry = False
                retry_reason = "none"
                
                if "VERIFIER_FAIL" in reasons_set or verifier_status == "fail":
                    should_retry = True
                    retry_reason = "VERIFIER_FAIL"
                elif "SEARCH_MISMATCH" in reasons_set and "patch_outside_locked_span" not in reasons_set:
                    should_retry = True
                    retry_reason = "SEARCH_MISMATCH"
                    
                if should_retry and controls.get("locked_search"):
                    from nexus.services.local_heal.failure_feedback_builder import build_failure_feedback
                    stdout_tail = solve_resp.verifier_receipt.stdout_tail if solve_resp.verifier_receipt else ""
                    stderr_tail = solve_resp.verifier_receipt.stderr_tail if solve_resp.verifier_receipt else ""
                    
                    feedback_prompt = build_failure_feedback(
                        task_id=request.task_id,
                        failure_class=retry_reason,
                        target_file=target_file,
                        target_symbol=target_symbol,
                        locked_search=locked_search,
                        previous_block_reason=fallback_block_reason,
                        verifier_status=verifier_status,
                        stdout_tail=stdout_tail,
                        stderr_tail=stderr_tail,
                    )
                    
                    retry_req = LocalModelCandidateRequest(
                        task_id=request.task_id,
                        problem_statement=request.problem_statement,
                        evidence_refs=request.evidence_refs,
                        prompt=feedback_prompt,
                    )
                    retry_resp = LocalModelCandidateAdapter.run(retry_req, provider=provider)
                    
                    solve_req_2 = IsolatedLocalSolveRequest(
                        task_id=request.task_id,
                        source_root=controls["source_root"],
                        problem_statement=request.problem_statement,
                        evidence_refs=request.evidence_refs,
                        model_output=retry_resp.candidate_text,
                        verifier_command=tuple(controls["verifier_command"]),
                        work_dir=controls["work_dir"],
                        local_model_called=retry_resp.local_model_called,
                        mutation_allowed=bool(signal_snapshot.get("mutation_allowed", False)),
                        verifier_allowed=bool(signal_snapshot.get("verifier_allowed", False)),
                        target_file=controls["target_file"],
                        target_symbol=controls["target_symbol"],
                        locked_search=controls["locked_search"],
                    )
                    solve_resp_2 = run_isolated_local_solve_loop(solve_req_2)
                    
                    gate_passed = solve_resp_2.capability_payload.get("gate_passed", False)
                    verifier_status_2 = solve_resp_2.capability_payload["metadata"].get("verifier_status", "not_run")
                    retry_success = (gate_passed is True and verifier_status_2 == "pass")
                    
                    solve_resp = solve_resp_2
                    attempt_count = 2
                    retry_attempted = True
                else:
                    attempt_count = 1
                    retry_attempted = False
                    retry_success = False
                    
                metadata = dict(solve_resp.capability_payload.get("metadata", {}))
                metadata.update({
                    "attempt_count": attempt_count,
                    "retry_attempted": retry_attempted,
                    "retry_reason": retry_reason,
                    "retry_success": retry_success,
                    "final_failure_class": solve_resp.hybrid_route.fallback_block_reason if solve_resp.hybrid_route.fallback_block_reason else "none",
                })
                solve_resp.capability_payload["metadata"] = metadata
                
                decision = solve_resp.hybrid_route
                capability_payload = solve_resp.capability_payload
                payload = decision.to_dict()
                invoked = True
                
        elif candidate_enabled:
            cand_blockers = []
            if not call_allowed:
                cand_blockers.append("model_call_not_allowed")
                
            provider = build_local_model_provider(
                signal_snapshot, controls, "candidate_generate_fn"
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
                "model_name": signal_snapshot.get("executor_model", ""),
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
            capability_payload = capability_payload_from_hybrid_route(decision)
            
        elif advisory_enabled:
            advis_blockers = []
            if not call_allowed:
                advis_blockers.append("model_call_not_allowed")
                
            provider = build_local_model_provider(
                signal_snapshot, controls, "advisory_generate_fn"
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
                "model_name": str(signal_snapshot.get("executor_model", "")),
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
            capability_payload = capability_payload_from_hybrid_route(decision)
            
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
            capability_payload = capability_payload_from_hybrid_route(decision)
            
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
            capability_payload = capability_payload_from_hybrid_route(decision)
            
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
            
        fail_closed_enabled = bool(signal_snapshot.get("fail_closed_enabled", False)) if signal_snapshot else False
        if fail_closed_enabled:
            vr_val = payload.get("verifier_result")
            vr_str = vr_val.value if hasattr(vr_val, "value") else str(vr_val) if vr_val else "not_run"
            
            vr_str_in = controls.get("verifier_result", vr_str)
            sel_hash_in = controls.get("selected_candidate_hash", payload.get("selected_candidate_hash", ""))
            app_hash_in = controls.get("applied_patch_hash", payload.get("applied_patch_hash", ""))
            guard_input = LocalGuardInput(
                task_id=request.task_id,
                route_payload=payload,
                evidence_refs=payload.get("evidence_refs", ()),
                verifier_result=vr_str_in,
                selected_candidate_hash=sel_hash_in,
                applied_patch_hash=app_hash_in,
                route_truth_source="CapabilityPlanner",
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
