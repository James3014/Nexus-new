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
from nexus.services.local_heal.local_model_armor_receipt_gate import validate_local_model_armor_metadata
from nexus.services.local_heal.local_model_capability_context import LocalModelCapabilityContext, CapabilityExecutionResult


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


def _resolve_execution_topology(request: LocalModelExecutorRequest) -> str:
    """Resolve execution topology with planner-owned signal_snapshot as first priority.
    
    Resolution order:
    1. request.route_context["signal_snapshot"]["execution_topology"] (planner-owned)
    2. request.route_context["execution_topology"] (top-level fallback)
    3. request.execution_topology (request field)
    4. "single_local_model" (hardcoded default)
    """
    route_ctx = request.route_context if isinstance(request.route_context, dict) else {}
    
    signal_snapshot = route_ctx.get("signal_snapshot")
    if not isinstance(signal_snapshot, dict):
        signal_snapshot = {}
    
    topology = signal_snapshot.get("execution_topology")
    if topology:
        return str(topology)
    
    topology = route_ctx.get("execution_topology")
    if topology:
        return str(topology)
    
    topology = request.execution_topology
    if topology:
        return str(topology)
    
    return "single_local_model"


class LocalModelExecutor:
    @staticmethod
    def run(request: LocalModelExecutorRequest, *, provider: LocalModelProvider | None = None) -> LocalModelExecutorResponse:
        empty_hash = hashlib.sha256(b"").hexdigest()
        
        execution_topology = _resolve_execution_topology(request)
        
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

        # 4. Handle Active Memory Retrieval if enabled
        selected_caps = request.selected_capabilities
        lessons = []
        if "memory" in selected_caps:
            try:
                from nexus.services.local_heal.memory_retrieval_adapter import MemoryRetrievalAdapter
                adapter = MemoryRetrievalAdapter(enabled=True)
                lessons = adapter.retrieve_reranked(
                    query_text=request.problem_statement,
                    anchor_symbol=request.route_context.get("target_symbol") or "",
                    anchor_file=request.target_file,
                    limit=3,
                    max_chars=800,
                    task_id=request.task_id
                )
            except Exception:
                pass

        memory_context = ""
        if lessons:
            memory_context = "\n\n=== RELEVANT HISTORICAL LESSONS ===\n"
            for idx, lesson in enumerate(lessons, 1):
                content = ""
                if hasattr(lesson, "summary"):
                    content = lesson.summary
                elif hasattr(lesson, "content"):
                    content = lesson.content
                else:
                    content = str(lesson)
                memory_context += f"Lesson {idx}: {content}\n"
            memory_context += "====================================\n"

        # 5. Source Anchor Context
        target_file = request.target_file
        target_symbol = request.route_context.get("target_symbol") or ""
        locked_search = request.route_context.get("locked_search") or ""
        
        source_anchor_hash = ""
        source_anchor_present = False
        source_anchor_source = "none"
        
        if locked_search and str(locked_search).strip():
            locked_text = locked_search if isinstance(locked_search, str) else str(locked_search)
            source_anchor_hash = hashlib.sha256(locked_text.encode("utf-8")).hexdigest()
            source_anchor_present = True
            source_anchor_source = "locked_search"
        elif target_file and target_symbol:
            try:
                from nexus.services.local_heal.local_model_source_anchor import build_local_model_source_anchor
                anchor = build_local_model_source_anchor(
                    source_root=request.repo_root,
                    target_file=target_file,
                    target_symbol=target_symbol,
                    locked_search="",
                )
                if anchor.span_hash:
                    source_anchor_hash = anchor.span_hash
                    source_anchor_present = True
                    source_anchor_source = anchor.canonical_span_source or "ast_boundary"
            except Exception:
                source_anchor_present = False
                source_anchor_source = "localizer_failed"
        
        # 6. Failure Feedback Context
        failure_feedback_present = False
        failure_feedback_text = ""
        route_ctx = request.route_context if isinstance(request.route_context, dict) else {}
        previous_failure = (
            route_ctx.get("previous_failure")
            or route_ctx.get("failure_reason")
            or route_ctx.get("verifier_failure")
            or route_ctx.get("verifier_output")
            or ""
        )
        if previous_failure and str(previous_failure).strip():
            try:
                from nexus.services.local_heal.failure_feedback_builder import build_failure_feedback
                failure_feedback_text = build_failure_feedback(
                    task_id=request.task_id,
                    failure_class=str(route_ctx.get("failure_class", "unknown")),
                    target_file=target_file,
                    target_symbol=target_symbol,
                    locked_search=locked_search,
                    previous_block_reason=str(previous_failure),
                    verifier_status=str(route_ctx.get("verifier_status", "fail")),
                    stdout_tail=str(route_ctx.get("stdout_tail", "")),
                    stderr_tail=str(route_ctx.get("stderr_tail", "")),
                )
                failure_feedback_present = True
            except Exception:
                failure_feedback_present = False
        
        # 7. Handle Execution Topology Branching
        if execution_topology == "local_committee_only":
            protocol_mode = os.environ.get("NEXUS_PROTOCOL_MODE", "anchored_edit")
            
            # Build enhanced problem statement with source anchor + failure feedback
            enhanced_problem = request.problem_statement
            if source_anchor_present:
                enhanced_problem += f"\n\nSource Anchor (target: {target_file}:{target_symbol}, hash: {source_anchor_hash[:16]}...)"
            if locked_search:
                enhanced_problem += f"\nLocked Search Span:\n```\n{locked_search}\n```"
            if failure_feedback_present and failure_feedback_text:
                enhanced_problem += f"\n\n{failure_feedback_text}"
            enhanced_problem += memory_context
            
            from nexus.services.local_heal.local_committee_candidate_provider import LocalCommitteeCandidateProvider
            from nexus.services.local_heal.candidate_decision_adapter import CandidateDecisionAdapter
            
            candidates = LocalCommitteeCandidateProvider.generate_committee_candidates(
                task_id=request.task_id,
                problem_statement=enhanced_problem,
                target_file=request.target_file,
                target_symbol=target_symbol,
                locked_search=locked_search,
                evidence_refs=request.evidence_refs,
                provider=provider,
                protocol_mode=protocol_mode,
            )
            
            # Build context for capability executors
            cap_ctx = LocalModelCapabilityContext(
                task_id=request.task_id,
                source_root=request.repo_root,
                problem_statement=enhanced_problem,
                target_file=target_file,
                target_symbol=target_symbol,
                selected_capabilities=selected_caps,
                execution_topology=execution_topology,
                evidence_refs=request.evidence_refs,
                source_anchor={"present": source_anchor_present, "source": source_anchor_source, "hash": source_anchor_hash},
                failure_feedback=failure_feedback_text,
                verifier_command=tuple(request.route_context.get("verifier_command", []) or []),
                candidate_pool=candidates,
                route_context=request.route_context,
                local_model_metadata={},
            )

            decision = CandidateDecisionAdapter.select_candidate(
                candidates,
                selected_capabilities=selected_caps,
                ctx=cap_ctx,
            )
            
            # Local model is called if at least one candidate wasn't blocked/abstained
            local_model_called = any(not c.abstained for c in candidates)
            
            selected_patch = decision.selected_candidate_patch
            patch_meta = {}
            if selected_patch.strip():
                selected_patch, patch_meta = _normalize_candidate_patch(request, locked_search, selected_patch)
                selected_hash = hashlib.sha256(selected_patch.encode("utf-8")).hexdigest() if selected_patch.strip() else empty_hash
            else:
                selected_hash = empty_hash
                
            provider_name = "ollama" if isinstance(provider, OllamaLocalModelProvider) else "injected"
            
            # Resolve selected model name or fallback to "committee"
            selected_model = ""
            for c in candidates:
                if c.candidate_id == decision.selected_candidate_id:
                    selected_model = c.model
                    break
            if not selected_model:
                selected_model = "committee"
                
            # Run gate executors for selected gate capabilities
            gate_results: dict[str, CapabilityExecutionResult] = {}
            for gate_name in ("artifact_gate", "claim_gate", "delivery_gate"):
                if gate_name in selected_caps:
                    from nexus.services.local_heal.local_model_capability_executors import (
                        ArtifactGateLocalExecutor, ClaimGateLocalExecutor, DeliveryGateLocalExecutor,
                    )
                    gate_executors = {
                        "artifact_gate": ArtifactGateLocalExecutor,
                        "claim_gate": ClaimGateLocalExecutor,
                        "delivery_gate": DeliveryGateLocalExecutor,
                    }
                    gate_results[gate_name] = gate_executors[gate_name]().execute(cap_ctx)

            ddtree_invoked = decision.ddtree_result.invoked if decision.ddtree_result else False
            autoreason_invoked = decision.autoreason_result.invoked if decision.autoreason_result else False

            raw_meta = {
                "execution_topology": "local_committee_only",
                "committee_candidate_count": len(candidates),
                "selected_candidate_id": decision.selected_candidate_id,
                "selected_by": decision.selected_by,
                "final_authority": decision.final_authority,
                "selected_capabilities_used": list(selected_caps),
                "protocol_normalization": patch_meta,
                "source_anchor_present": source_anchor_present,
                "source_anchor_source": source_anchor_source,
                "source_anchor_hash": source_anchor_hash[:16] if source_anchor_hash else "",
                "target_file": target_file,
                "target_symbol": target_symbol,
                "locked_search_present": bool(locked_search.strip()),
                "failure_feedback_present": failure_feedback_present,
                "protocol_mode": "anchored_edit",
                "ddtree_invoked": ddtree_invoked,
                "autoreason_invoked": autoreason_invoked,
                "ddtree_result": decision.ddtree_result.to_receipt_dict() if decision.ddtree_result else None,
                "autoreason_result": decision.autoreason_result.to_receipt_dict() if decision.autoreason_result else None,
                "artifact_gate_invoked": gate_results.get("artifact_gate", CapabilityExecutionResult(name="artifact_gate", selected=False, invoked=False, gate_passed=False, outcome_contributed=False, evidence_present=False)).invoked,
                "claim_gate_invoked": gate_results.get("claim_gate", CapabilityExecutionResult(name="claim_gate", selected=False, invoked=False, gate_passed=False, outcome_contributed=False, evidence_present=False)).invoked,
                "delivery_gate_invoked": gate_results.get("delivery_gate", CapabilityExecutionResult(name="delivery_gate", selected=False, invoked=False, gate_passed=False, outcome_contributed=False, evidence_present=False)).invoked,
                "artifact_gate_passed": gate_results.get("artifact_gate", CapabilityExecutionResult(name="artifact_gate", selected=False, invoked=False, gate_passed=False, outcome_contributed=False, evidence_present=False)).gate_passed,
                "claim_gate_passed": gate_results.get("claim_gate", CapabilityExecutionResult(name="claim_gate", selected=False, invoked=False, gate_passed=False, outcome_contributed=False, evidence_present=False)).gate_passed,
                "delivery_gate_passed": gate_results.get("delivery_gate", CapabilityExecutionResult(name="delivery_gate", selected=False, invoked=False, gate_passed=False, outcome_contributed=False, evidence_present=False)).gate_passed,
                "gate_results": {k: v.to_receipt_dict() for k, v in gate_results.items()},
            }
            armor_ok, armor_miss = validate_local_model_armor_metadata(raw_meta)
            raw_meta["armor_receipt_complete"] = armor_ok
            raw_meta["armor_receipt_missing_fields"] = armor_miss
            return LocalModelExecutorResponse(
                invoked=True,
                local_model_called=local_model_called,
                candidate_patch=selected_patch,
                candidate_hash=selected_hash,
                reasoning_summary=f"selected_by_{decision.selected_by}",
                raw_model_metadata=raw_meta,
                provider=provider_name,
                model_name=selected_model,
                error="",
                timeout=False,
                evidence_refs=decision.decision_evidence_refs or request.evidence_refs,
            )

        # 8. LocalHeal Pipeline topology
        if execution_topology == "localheal_pipeline":
            from nexus.services.local_heal.local_model_capability_executors import (
                LocalHealPipelineCapabilityExecutor,
                DDTreeLocalExecutor,
                AutoreasonLocalExecutor,
                ArtifactGateLocalExecutor,
                ClaimGateLocalExecutor,
                DeliveryGateLocalExecutor,
            )

            # Execute repair_loop (localheal pipeline bridge)
            repair_exec = LocalHealPipelineCapabilityExecutor().execute(cap_ctx)

            # Execute ddtree/autoreason/gates for this topology
            ddtree_exec = DDTreeLocalExecutor().execute(cap_ctx)
            autoreason_exec = AutoreasonLocalExecutor().execute(cap_ctx)
            artifact_exec = ArtifactGateLocalExecutor().execute(cap_ctx)
            claim_exec = ClaimGateLocalExecutor().execute(cap_ctx)
            delivery_exec = DeliveryGateLocalExecutor().execute(cap_ctx)

            raw_meta = {
                "execution_topology": "localheal_pipeline",
                "selected_capabilities_used": list(selected_caps),
                "protocol_mode": "anchored_edit",
                "source_anchor_present": source_anchor_present,
                "source_anchor_source": source_anchor_source,
                "source_anchor_hash": source_anchor_hash[:16] if source_anchor_hash else "",
                "target_file": target_file,
                "target_symbol": target_symbol,
                "locked_search_present": bool(locked_search.strip()),
                "failure_feedback_present": failure_feedback_present,
                "final_authority": "NexusVerifier",
                "ddtree_invoked": ddtree_exec.invoked,
                "autoreason_invoked": autoreason_exec.invoked,
                "artifact_gate_invoked": artifact_exec.invoked,
                "claim_gate_invoked": claim_exec.invoked,
                "delivery_gate_invoked": delivery_exec.invoked,
                "localheal_pipeline_invoked": repair_exec.telemetries.get("localheal_pipeline_invoked", False),
                "committee_orchestrator_invoked": repair_exec.telemetries.get("committee_orchestrator_invoked", False),
                "solid_search_replace_protocol_available": repair_exec.telemetries.get("solid_search_replace_protocol_available", False),
                "granular_localizer_available": repair_exec.telemetries.get("granular_localizer_available", False),
                "failure_feedback_builder_available": repair_exec.telemetries.get("failure_feedback_builder_available", False),
                "evaluation_gate_available": repair_exec.telemetries.get("evaluation_gate_available", False),
                "semantic_retry_available": repair_exec.telemetries.get("semantic_retry_available", False),
            }
            armor_ok, armor_miss = validate_local_model_armor_metadata(raw_meta)
            raw_meta["armor_receipt_complete"] = armor_ok
            raw_meta["armor_receipt_missing_fields"] = armor_miss

            # Use single_local_model provider path for candidate generation
            protocol_mode = os.environ.get("NEXUS_PROTOCOL_MODE", "anchored_edit")
            failure_context = ""
            if failure_feedback_present and failure_feedback_text:
                failure_context = f"\n\n{failure_feedback_text}"

            if protocol_mode == "anchored_edit":
                explicit_prompt = (
                    f"You are generating a replacement code block to solve a coding task.\n"
                    f"Problem: {request.problem_statement}{memory_context}{failure_context}\n"
                    f"Target File: {target_file}\n"
                    f"Target Symbol: {target_symbol}\n"
                    f"Source Anchor Hash: {source_anchor_hash[:16] if source_anchor_hash else 'none'}\n"
                    f"Locked Search Span that will be replaced:\n"
                    f"```\n{locked_search}\n```\n\n"
                    f"Provide the replacement code inside a REPLACE block exactly like this:\n"
                    f"<<<<<<< REPLACE\n"
                    f"[replacement code goes here]\n"
                    f">>>>>>> REPLACE\n\n"
                    f"Do not include any other text outside the REPLACE block.\n"
                )
            else:
                explicit_prompt = (
                    f"You are generating a unified diff to fix a bug in {target_file}.\n"
                    f"Problem: {request.problem_statement}{memory_context}{failure_context}\n"
                    f"Target File: {target_file}\n"
                    f"Target Symbol: {target_symbol}\n"
                    f"Return ONLY the diff. No prose.\n"
                )

            prov_req = LocalModelProviderRequest(
                task_id=request.task_id,
                prompt=explicit_prompt,
                evidence_refs=request.evidence_refs,
                model_name=request.model_name or os.environ.get("NEXUS_LOCAL_MODEL_NAME", "qwen2.5-coder:7b"),
            )
            prov_resp = provider.generate(prov_req)

            candidate_patch = prov_resp.output_text
            patch_meta = {}
            if candidate_patch.strip():
                candidate_patch, patch_meta = _normalize_candidate_patch(request, locked_search, candidate_patch)
                candidate_hash = hashlib.sha256(candidate_patch.encode("utf-8")).hexdigest() if candidate_patch.strip() else empty_hash
            else:
                candidate_hash = empty_hash

            provider_name = "ollama" if isinstance(provider, OllamaLocalModelProvider) else "injected"

            return LocalModelExecutorResponse(
                invoked=prov_resp.provider_invoked,
                local_model_called=prov_resp.model_called,
                candidate_patch=candidate_patch,
                candidate_hash=candidate_hash,
                reasoning_summary="success" if not prov_resp.error else "failed",
                raw_model_metadata=raw_meta,
                provider=provider_name,
                model_name=prov_resp.model_name or prov_req.model_name,
                error=prov_resp.error,
                timeout=prov_resp.timed_out,
                evidence_refs=request.evidence_refs,
            )

        # 9. Generate Candidate Patch for single_local_model
        protocol_mode = os.environ.get("NEXUS_PROTOCOL_MODE", "standard")
        
        # Build failure feedback context for prompt
        failure_context = ""
        if failure_feedback_present and failure_feedback_text:
            failure_context = f"\n\n{failure_feedback_text}"
        
        if protocol_mode == "anchored_edit":
            explicit_prompt = (
                f"You are generating a replacement code block to solve a coding task.\n"
                f"Problem: {request.problem_statement}{memory_context}{failure_context}\n"
                f"Target File: {target_file}\n"
                f"Target Symbol: {target_symbol}\n"
                f"Source Anchor Hash: {source_anchor_hash[:16] if source_anchor_hash else 'none'}\n"
                f"Locked Search Span that will be replaced:\n"
                f"```\n{locked_search}\n```\n\n"
                f"Provide the replacement code inside a REPLACE block exactly like this:\n"
                f"<<<<<<< REPLACE\n"
                f"[replacement code goes here]\n"
                f">>>>>>> REPLACE\n\n"
                f"Do not include any other text, explanation, markdown formatting, or markdown code fences outside the REPLACE block.\n"
            )
        else:

            # Read surrounding context from the actual file
            source_context = ""
            try:
                from pathlib import Path as _Path
                _fp = _Path(request.repo_root) / request.target_file if request.repo_root else _Path(request.target_file)
                if _fp.exists():
                    _lines = _fp.read_text(encoding="utf-8").splitlines()
                    # Find locked_search start line
                    _search_first = locked_search.strip().splitlines()[0].strip() if locked_search.strip() else ""
                    _anchor_line = 1
                    for _i, _l in enumerate(_lines, 1):
                        if _search_first and _search_first in _l:
                            _anchor_line = _i
                            break
                    # Show ±15 lines around anchor
                    _start = max(0, _anchor_line - 16)
                    _end = min(len(_lines), _anchor_line + 20)
                    numbered = "\n".join(f"{_start+_j+1}: {_lines[_start+_j]}" for _j in range(_end - _start))
                    source_context = f"\nRelevant source lines (with line numbers):\n```python\n{numbered}\n```\n"
            except Exception:
                pass

            context_block = ""
            if locked_search.strip():
                context_block = (
                    f"\nThe code to be changed (locked search span):\n"
                    f"```python\n{locked_search}\n```\n"
                )

            explicit_prompt = (
                f"You are generating a unified diff to fix a bug in {request.target_file}.\n"
                f"Problem: {request.problem_statement}{memory_context}{failure_context}\n"
                f"Target File: {request.target_file}\n"
                f"Target Symbol: {target_symbol}\n"
                f"Source Anchor Hash: {source_anchor_hash[:16] if source_anchor_hash else 'none'}\n"
                f"{context_block}"
                f"{source_context}\n"
                f"IMPORTANT RULES:\n"
                f"1. The diff header MUST use exactly: --- a/{request.target_file}  and  +++ b/{request.target_file}\n"
                f"2. The @@ hunk header MUST use the EXACT line numbers from the source above.\n"
                f"3. Context lines (no +/-) MUST EXACTLY match the source file character-for-character including indentation.\n"
                f"4. Return ONLY the diff wrapped in a ```diff fenced block. No prose, no explanation.\n"
            )

        
        prov_req = LocalModelProviderRequest(
            task_id=request.task_id,
            prompt=explicit_prompt,
            evidence_refs=request.evidence_refs,
            model_name=request.model_name or os.environ.get("NEXUS_LOCAL_MODEL_NAME", "qwen2.5-coder:7b"),
        )
        
        prov_resp = provider.generate(prov_req)
        
        candidate_patch = prov_resp.output_text
        patch_meta = {}
        if candidate_patch.strip():
            candidate_patch, patch_meta = _normalize_candidate_patch(request, locked_search, candidate_patch)
            candidate_hash = hashlib.sha256(candidate_patch.encode("utf-8")).hexdigest() if candidate_patch.strip() else empty_hash
        else:
            candidate_hash = empty_hash
            
        provider_name = "ollama" if isinstance(provider, OllamaLocalModelProvider) else "injected"
        
        raw_meta = {
            "output_truncated": prov_resp.output_truncated,
            "error": prov_resp.error,
            "protocol_mode": protocol_mode,
            "execution_topology": execution_topology,
            "protocol_normalization": patch_meta,
            "source_anchor_present": source_anchor_present,
            "source_anchor_source": source_anchor_source,
            "source_anchor_hash": source_anchor_hash[:16] if source_anchor_hash else "",
            "target_file": target_file,
            "target_symbol": target_symbol,
            "locked_search_present": bool(locked_search.strip()),
            "failure_feedback_present": failure_feedback_present,
            "final_authority": "NexusVerifier",
        }
        armor_ok, armor_miss = validate_local_model_armor_metadata(raw_meta)
        raw_meta["armor_receipt_complete"] = armor_ok
        raw_meta["armor_receipt_missing_fields"] = armor_miss
        return LocalModelExecutorResponse(
            invoked=prov_resp.provider_invoked,
            local_model_called=prov_resp.model_called,
            candidate_patch=candidate_patch,
            candidate_hash=candidate_hash,
            reasoning_summary="success" if not prov_resp.error else "failed",
            raw_model_metadata=raw_meta,
            provider=provider_name,
            model_name=prov_resp.model_name or prov_req.model_name,
            error=prov_resp.error,
            timeout=prov_resp.timed_out,
            evidence_refs=request.evidence_refs,
        )


def _normalize_candidate_patch(
    request: LocalModelExecutorRequest,
    locked_search: str,
    candidate_patch: str,
) -> tuple[str, dict]:
    """Normalize candidate_patch to standard unified diff using SolidSearchReplaceProtocol.
    
    Returns:
        (normalized_patch, metadata) where metadata contains protocol_parse_failed if error.
    """
    # Defensive: ensure strings, not bytes
    locked_search = locked_search if isinstance(locked_search, str) else str(locked_search) if locked_search else ""
    candidate_patch = candidate_patch if isinstance(candidate_patch, str) else str(candidate_patch) if candidate_patch else ""
    
    if not candidate_patch.strip():
        return "", {"protocol_parse_failed": True, "error": "empty_patch"}
    
    # 1. Already standard unified diff — pass through
    if "--- a/" in candidate_patch and "+++ b/" in candidate_patch and "<<<<<<< REPLACE" not in candidate_patch:
        return candidate_patch, {"protocol_used": "passthrough", "normalized": False}
    
    # 2. Use SolidSearchReplaceProtocol to parse REPLACE block
    from nexus.services.local_heal.protocol import SolidSearchReplaceProtocol, PatchError
    
    protocol = SolidSearchReplaceProtocol()
    anchor_text = locked_search if locked_search.strip() else None
    
    # Temporarily set protocol_mode to anchored_edit for parsing
    import os
    old_mode = os.environ.get("NEXUS_PROTOCOL_MODE")
    os.environ["NEXUS_PROTOCOL_MODE"] = "anchored_edit"
    try:
        result = protocol.parse(candidate_patch, anchor_text=anchor_text)
    finally:
        if old_mode is None:
            os.environ.pop("NEXUS_PROTOCOL_MODE", None)
        else:
            os.environ["NEXUS_PROTOCOL_MODE"] = old_mode
    
    # 3. Handle parse error — fail closed
    if isinstance(result, PatchError):
        return "", {
            "protocol_parse_failed": True,
            "error_kind": result.kind.name if hasattr(result.kind, "name") else str(result.kind),
            "error_message": result.message,
        }
    
    # 4. Got PatchIntent(s) — extract replacement from first intent
    if not result:
        return "", {"protocol_parse_failed": True, "error": "no_intents"}
    
    intent = result[0]
    replacement = intent.replace
    
    if not replacement.strip():
        return "", {"protocol_parse_failed": True, "error": "empty_replacement"}
    
    # 5. Generate unified diff from locked_search → replacement
    import difflib
    import re as _re
    
    _anchor_line = 1
    if locked_search and str(locked_search).strip():
        try:
            from pathlib import Path as _Path
            _fp = _Path(request.repo_root) / request.target_file if request.repo_root else _Path(request.target_file)
            if _fp.exists():
                _lines = _fp.read_text(encoding="utf-8").splitlines()
                _search_first = str(locked_search).strip().splitlines()[0].strip()
                for _i, _l in enumerate(_lines, 1):
                    if _search_first in _l:
                        _anchor_line = _i
                        break
        except Exception:
            pass
    
    locked_lines = str(locked_search).splitlines(keepends=True)
    replace_lines = str(replacement).splitlines(keepends=True)
    
    locked_lines = [l if l.endswith("\n") else l + "\n" for l in locked_lines]
    replace_lines = [l if l.endswith("\n") else l + "\n" for l in replace_lines]
    
    diff_gen = difflib.unified_diff(
        locked_lines,
        replace_lines,
        fromfile=f"a/{request.target_file}",
        tofile=f"b/{request.target_file}",
        lineterm="\n"
    )
    
    adjusted_lines = []
    for line in diff_gen:
        if line.startswith("@@"):
            m = _re.match(r"@@ -(\d+),(\d+) \+(\d+),(\d+) @@(.*)", line)
            if m:
                old_start = int(m.group(1))
                old_len = int(m.group(2))
                new_start = int(m.group(3))
                new_len = int(m.group(4))
                extra = m.group(5)
                adj_old = _anchor_line + old_start - 1
                adj_new = _anchor_line + new_start - 1
                line = f"@@ -{adj_old},{old_len} +{adj_new},{new_len} @@{extra}\n"
        adjusted_lines.append(line)
    
    normalized = "".join(adjusted_lines)
    return normalized, {"protocol_used": "solid_search_replace", "normalized": True}
