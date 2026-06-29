from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import os
from typing import Any, Mapping

from nexus.services.local_heal.local_model_provider import (
    LocalModelProvider,
    LocalModelProviderRequest,
    InertLocalModelProvider,
    OllamaLocalModelProvider,
    InjectedLocalModelProvider,
)
from nexus.services.local_heal.capability_adapter import build_local_model_provider_from_env


@dataclass(frozen=True)
class LocalModelExecutorRequest:
    task_id: str
    problem_statement: str
    repo_root: str
    target_file: str
    selected_capabilities: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    receipt_context: dict[str, Any] = field(default_factory=dict)
    route_context: dict[str, Any] = field(default_factory=dict)
    model_name: str = ""
    dry_run: bool = True
    mutation_allowed: bool = False
    verifier_allowed: bool = False
    execution_topology: str = "single_local_model"


@dataclass(frozen=True)
class LocalModelExecutorResponse:
    invoked: bool
    local_model_called: bool
    candidate_patch: str
    candidate_hash: str
    reasoning_summary: str
    raw_model_metadata: dict[str, Any]
    provider: str
    model_name: str
    error: str
    timeout: bool
    evidence_refs: tuple[str, ...]


class LocalModelExecutor:
    @staticmethod
    def run(request: LocalModelExecutorRequest, *, provider: LocalModelProvider | None = None) -> LocalModelExecutorResponse:
        empty_hash = hashlib.sha256(b"").hexdigest()
        
        execution_topology = os.environ.get("NEXUS_LOCAL_MODEL_EXECUTOR_TOPOLOGY") or request.execution_topology or "single_local_model"
        
        # 1. Handle Dry Run
        if request.dry_run:
            return LocalModelExecutorResponse(
                invoked=False,
                local_model_called=False,
                candidate_patch="",
                candidate_hash=empty_hash,
                reasoning_summary="dry_run_active",
                raw_model_metadata={"dry_run": True, "execution_topology": execution_topology},
                provider="none",
                model_name="",
                error="dry_run",
                timeout=False,
                evidence_refs=request.evidence_refs,
            )

        # 2. Build Provider
        if provider is None:
            provider = build_local_model_provider_from_env(
                os.environ,
                request.route_context,
                "candidate_generate_fn"
            )

        # 3. Check Provider Availability
        if isinstance(provider, InertLocalModelProvider):
            return LocalModelExecutorResponse(
                invoked=True,
                local_model_called=False,
                candidate_patch="",
                candidate_hash=empty_hash,
                reasoning_summary="provider_unavailable",
                raw_model_metadata={},
                provider="inert",
                model_name="",
                error="provider_unavailable",
                timeout=False,
                evidence_refs=request.evidence_refs,
            )

        # 4. Generate Candidate Patch
        protocol_mode = os.environ.get("NEXUS_PROTOCOL_MODE", "standard")
        
        if protocol_mode == "anchored_edit":
            locked_search = request.route_context.get("locked_search") or ""
            target_symbol = request.route_context.get("target_symbol") or ""
            explicit_prompt = (
                f"You are generating a replacement code block to solve a coding task.\n"
                f"Problem: {request.problem_statement}\n"
                f"Target File: {request.target_file}\n"
                f"Target Symbol: {target_symbol}\n"
                f"Locked Search Span that will be replaced:\n"
                f"```\n{locked_search}\n```\n\n"
                f"Provide the replacement code inside a REPLACE block exactly like this:\n"
                f"<<<<<<< REPLACE\n"
                f"[replacement code goes here]\n"
                f">>>>>>> REPLACE\n\n"
                f"Do not include any other text, explanation, markdown formatting, or markdown code fences outside the REPLACE block.\n"
            )
        else:
            # Construct explicit prompt to output standard unified diff
            explicit_prompt = (
                f"You are generating a unified diff to solve a coding task.\n"
                f"Problem: {request.problem_statement}\n"
                f"Target File: {request.target_file}\n"
                f"Return only a standard unified diff wrapped in fenced ```diff block.\n"
                f"Do not include any prose, explanation, or extra commentary.\n"
            )
        
        prov_req = LocalModelProviderRequest(
            task_id=request.task_id,
            prompt=explicit_prompt,
            evidence_refs=request.evidence_refs,
            model_name=request.model_name or os.environ.get("NEXUS_LOCAL_MODEL_NAME", "qwen2.5-coder:7b"),
        )
        
        prov_resp = provider.generate(prov_req)
        
        candidate_patch = prov_resp.output_text
        if candidate_patch.strip():
            candidate_hash = hashlib.sha256(candidate_patch.encode("utf-8")).hexdigest()
        else:
            candidate_hash = empty_hash
            
        provider_name = "ollama" if isinstance(provider, OllamaLocalModelProvider) else "injected"
        
        return LocalModelExecutorResponse(
            invoked=prov_resp.provider_invoked,
            local_model_called=prov_resp.model_called,
            candidate_patch=candidate_patch,
            candidate_hash=candidate_hash,
            reasoning_summary="success" if not prov_resp.error else "failed",
            raw_model_metadata={
                "output_truncated": prov_resp.output_truncated,
                "error": prov_resp.error,
                "protocol_mode": protocol_mode,
                "execution_topology": execution_topology,
            },
            provider=provider_name,
            model_name=prov_resp.model_name or prov_req.model_name,
            error=prov_resp.error,
            timeout=prov_resp.timed_out,
            evidence_refs=request.evidence_refs,
        )
