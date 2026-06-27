from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from nexus.contracts.hybrid_route import RouteMode, Authority


@dataclass(frozen=True)
class LocalGuardInput:
    task_id: str
    route_payload: Mapping[str, Any]
    evidence_refs: tuple[str, ...] = ()
    verifier_result: str = "not_run"
    selected_candidate_hash: str = ""
    applied_patch_hash: str = ""
    route_truth_source: str = "CapabilityPlanner"


@dataclass(frozen=True)
class LocalGuardDecision:
    guard_invoked: bool
    guard_blocked: bool
    blockers: tuple[str, ...]
    route_mode: RouteMode
    authority: Authority
    public_claim_allowed: bool = False
    production_ready: bool = False
    behavior_changed: bool = False
    adapter_output_is_route_truth: bool = False


def run_local_guard_fail_closed(guard_input: LocalGuardInput) -> LocalGuardDecision:
    blockers: list[str] = []
    payload = guard_input.route_payload
    
    if guard_input.route_truth_source != "CapabilityPlanner":
        blockers.append("invalid_route_truth_source")
        
    if bool(payload.get("public_claim_allowed", False)):
        blockers.append("public_claim_allowed_must_be_false")
        
    if bool(payload.get("production_ready", False)):
        blockers.append("production_ready_must_be_false")
        
    if bool(payload.get("adapter_output_is_route_truth", False)):
        blockers.append("adapter_output_is_route_truth_must_be_false")
        
    if guard_input.verifier_result == "pass" and not guard_input.evidence_refs:
        blockers.append("missing_evidence_refs")
        
    if guard_input.verifier_result == "fail":
        blockers.append("verifier_fail")
        
    sel_hash = guard_input.selected_candidate_hash.strip()
    app_hash = guard_input.applied_patch_hash.strip()
    if sel_hash and app_hash and sel_hash != app_hash:
        blockers.append("hash_mismatch")
        
    if blockers:
        return LocalGuardDecision(
            guard_invoked=True,
            guard_blocked=True,
            blockers=tuple(sorted(set(blockers))),
            route_mode=RouteMode.CLOUD_FIRST_LOCAL_GUARD_FAIL_CLOSED,
            authority=Authority.FAIL_CLOSED,
        )
    else:
        return LocalGuardDecision(
            guard_invoked=True,
            guard_blocked=False,
            blockers=(),
            route_mode=RouteMode.CLOUD_FIRST_LOCAL_GUARD_ADVISORY,
            authority=Authority.ADVISORY_ONLY,
        )
