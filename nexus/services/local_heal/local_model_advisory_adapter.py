from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from nexus.services.local_heal.local_model_provider import (
    LocalModelProvider,
    LocalModelProviderRequest,
    LocalModelProviderResponse,
    InertLocalModelProvider,
    InjectedLocalModelProvider,
)


@dataclass(frozen=True)
class LocalModelAdvisoryRequest:
    task_id: str
    problem_statement: str
    evidence_refs: tuple[str, ...]
    candidate_summary: str = ""
    route_truth_source: str = "CapabilityPlanner"
    attempt_id: str = ""
    execution_profile: str = ""
    phase: str = ""


@dataclass(frozen=True)
class LocalModelAdvisoryResponse:
    advisory_invoked: bool
    local_model_called: bool
    advisory_text: str
    advisory_blockers: tuple[str, ...]
    route_truth_source: str = "CapabilityPlanner"
    adapter_output_is_route_truth: bool = False
    behavior_changed: bool = False
    public_claim_allowed: bool = False
    production_ready: bool = False


class LocalModelAdvisoryAdapter:
    @staticmethod
    def run(
        request: LocalModelAdvisoryRequest,
        *,
        provider: LocalModelProvider | None = None,
        advisory_fn: Callable[[LocalModelAdvisoryRequest], str] | None = None,
    ) -> LocalModelAdvisoryResponse:
        
        if provider is None:
            if advisory_fn is not None:
                def wrapper(prov_req: LocalModelProviderRequest) -> str:
                    advis_req = LocalModelAdvisoryRequest(
                        task_id=prov_req.task_id,
                        problem_statement=prov_req.prompt,
                        evidence_refs=prov_req.evidence_refs,
                    )
                    return advisory_fn(advis_req)
                provider = InjectedLocalModelProvider(wrapper)
            else:
                provider = InertLocalModelProvider()
                
        prov_req = LocalModelProviderRequest(
            task_id=request.task_id,
            prompt=request.problem_statement,
            evidence_refs=request.evidence_refs,
            model_name="qwen",
            attempt_id=request.attempt_id,
            execution_profile=request.execution_profile,
            phase=request.phase,
        )
        
        prov_resp = provider.generate(prov_req)
        
        blockers = []
        if prov_resp.error:
            blockers.append(prov_resp.error)
        if type(provider) is InertLocalModelProvider:
            blockers.append("advisory_fn_missing")
            
        return LocalModelAdvisoryResponse(
            advisory_invoked=prov_resp.provider_invoked,
            local_model_called=prov_resp.model_called,
            advisory_text=prov_resp.output_text,
            advisory_blockers=tuple(sorted(set(blockers))),
        )
