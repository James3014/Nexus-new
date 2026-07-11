from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any

from nexus.services.local_heal.local_model_provider import (
    LocalModelProvider,
    LocalModelProviderRequest,
    LocalModelProviderResponse,
    InertLocalModelProvider,
)


@dataclass(frozen=True)
class LocalModelCandidateRequest:
    task_id: str
    problem_statement: str
    evidence_refs: tuple[str, ...]
    prompt: str
    model_name: str = ""
    attempt_id: str = ""
    execution_profile: str = ""
    phase: str = ""


@dataclass(frozen=True)
class LocalModelCandidateResponse:
    candidate_invoked: bool
    local_model_called: bool
    candidate_text: str
    candidate_id: str
    selected_candidate_hash: str
    candidate_output_isolated: bool = True
    applied_patch_hash: str = ""
    selected_candidate_hash_matches_applied: bool = False
    verifier_result: str = "not_run"
    public_claim_allowed: bool = False
    production_ready: bool = False
    adapter_output_is_route_truth: bool = False
    behavior_changed: bool = False
    blockers: tuple[str, ...] = ()


class LocalModelCandidateAdapter:
    @staticmethod
    def run(
        request: LocalModelCandidateRequest,
        *,
        provider: LocalModelProvider | None = None,
    ) -> LocalModelCandidateResponse:
        
        if provider is None:
            provider = InertLocalModelProvider()
            
        prov_req = LocalModelProviderRequest(
            task_id=request.task_id,
            prompt=request.prompt,
            evidence_refs=request.evidence_refs,
            model_name=request.model_name,
            attempt_id=request.attempt_id,
            execution_profile=request.execution_profile,
            phase=request.phase,
        )
        
        prov_resp = provider.generate(prov_req)
        
        candidate_text = prov_resp.output_text
        if candidate_text.strip():
            sel_hash = hashlib.sha256(candidate_text.encode("utf-8")).hexdigest()
        else:
            sel_hash = ""
            
        blockers = ["missing_applied_patch_hash", "selected_reapply_not_proven"]
        if prov_resp.error:
            blockers.append(prov_resp.error)
        if type(provider) is InertLocalModelProvider:
            blockers.append("candidate_provider_missing")
            
        return LocalModelCandidateResponse(
            candidate_invoked=prov_resp.provider_invoked,
            local_model_called=prov_resp.model_called,
            candidate_text=candidate_text,
            candidate_id=f"c-{request.task_id}",
            selected_candidate_hash=sel_hash,
            candidate_output_isolated=True,
            applied_patch_hash="",
            selected_candidate_hash_matches_applied=False,
            verifier_result="not_run",
            blockers=tuple(sorted(set(blockers))),
        )
