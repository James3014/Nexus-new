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
from nexus.services.local_heal.local_model_armor_receipt_gate import validate_local_model_armor_metadata
from nexus.services.local_heal.local_model_capability_context import LocalModelCapabilityContext, CapabilityExecutionResult
from nexus.services.local_heal.local_assist_receipts import build_local_assist_telemetry_from_executor_meta
from nexus.services.local_heal.candidate_isolation_gate import (
    CandidateIsolationReceipt,
    candidate_isolation_to_hybrid_route,
)
from nexus.services.local_heal.isolated_workspace_apply import (
    IsolatedApplyRequest,
    run_isolated_workspace_apply,
)
from nexus.services.local_heal.isolated_verifier import (
    IsolatedVerifierRequest,
    run_isolated_verifier,
)


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
    """Resolve execution topology strictly from planner-owned signal_snapshot.
    
    Resolution order:
    1. request.route_context["signal_snapshot"]["execution_topology"] (planner-owned)
    No fallbacks allowed. Missing or empty => raises ValueError.
    """
    route_ctx = request.route_context if isinstance(request.route_context, dict) else {}
    signal_snapshot = route_ctx.get("signal_snapshot")
    if not isinstance(signal_snapshot, dict):
        raise ValueError("Missing signal_snapshot in route_context")
    
    topology = signal_snapshot.get("execution_topology")
    if not topology:
        raise ValueError("Missing execution_topology in signal_snapshot")
        
    if "protocol_mode" not in signal_snapshot:
        raise ValueError("Missing protocol_mode in signal_snapshot")
        
    if topology != "local_committee_only":
        if "executor_model" not in signal_snapshot:
            raise ValueError("Missing executor_model in signal_snapshot")
    
    return str(topology)


def _project_pipeline_patch_to_target_file(unified_diff: str, target_file: str) -> tuple[str, dict[str, Any]]:
    """Keep only the target file section from a multi-file unified diff."""
    if not unified_diff.strip():
        return "", {"protocol_used": "pipeline_result", "normalized": False}

    target_norm = os.path.normpath(target_file)
    lines = unified_diff.splitlines()
    projected_sections: list[list[str]] = []
    current_section: list[str] = []
    current_target: str | None = None
    dropped_files: list[str] = []

    def _flush() -> None:
        nonlocal current_section, current_target
        if not current_section:
            return
        if current_target == target_norm:
            projected_sections.append(current_section[:])
        elif current_target:
            dropped_files.append(current_target)
        current_section = []
        current_target = None

    for line in lines:
        if line.startswith("--- a/"):
            _flush()
            current_target = os.path.normpath(line[len("--- a/"):].strip())
            current_section = [line]
            continue
        if current_section:
            current_section.append(line)
    _flush()

    projected_diff = "\n".join("\n".join(section) for section in projected_sections).strip()
    return projected_diff, {
        "protocol_used": "pipeline_result",
        "normalized": projected_diff != unified_diff.strip(),
        "target_file_only": True,
        "dropped_files": dropped_files,
    }


def _unwrap_outer_markdown_fence(candidate_patch: str) -> tuple[str, dict[str, Any]]:
    stripped = candidate_patch.strip()
    if not stripped.startswith("```"):
        return candidate_patch, {"outer_markdown_fence_unwrapped": False}

    lines = stripped.splitlines()
    if len(lines) < 3 or not lines[-1].strip().startswith("```"):
        return candidate_patch, {"outer_markdown_fence_unwrapped": False}

    inner = "\n".join(lines[1:-1]).strip()
    if not inner:
        return candidate_patch, {"outer_markdown_fence_unwrapped": False}

    return inner, {
        "outer_markdown_fence_unwrapped": True,
        "normalized": True,
    }


def _unwrap_markdown_fence_inside_replace_block(candidate_patch: str) -> tuple[str, dict[str, Any]]:
    replace_start = "<<<<<<< REPLACE"
    replace_end = ">>>>>>> REPLACE"
    if replace_start not in candidate_patch or replace_end not in candidate_patch:
        return candidate_patch, {"replace_block_markdown_fence_unwrapped": False}

    start_idx = candidate_patch.find(replace_start)
    content_start = start_idx + len(replace_start)
    end_idx = candidate_patch.find(replace_end, content_start)
    if end_idx == -1:
        return candidate_patch, {"replace_block_markdown_fence_unwrapped": False}

    replacement = candidate_patch[content_start:end_idx]
    stripped = replacement.strip()
    if not stripped.startswith("```"):
        return candidate_patch, {"replace_block_markdown_fence_unwrapped": False}

    lines = stripped.splitlines()
    if len(lines) < 3 or not lines[-1].strip().startswith("```"):
        return candidate_patch, {"replace_block_markdown_fence_unwrapped": False}

    inner = "\n".join(lines[1:-1]).strip()
    if not inner:
        return candidate_patch, {"replace_block_markdown_fence_unwrapped": False}

    rebuilt = (
        candidate_patch[:content_start]
        + "\n"
        + inner
        + "\n"
        + candidate_patch[end_idx:]
    )
    return rebuilt, {
        "replace_block_markdown_fence_unwrapped": True,
        "normalized": True,
    }


def build_local_model_provider_from_signal_snapshot(
    route_context: Mapping[str, Any],
    injected_fn_key: str,
) -> LocalModelProvider:
    """Factory to instantiate provider specified strictly by planner contract signal_snapshot.
    
    No route selection or fallback allowed. Missing required fields fails closed.
    """
    signal_snapshot = route_context.get("signal_snapshot", {}) if isinstance(route_context, dict) else {}
    if not isinstance(signal_snapshot, dict):
        return InertLocalModelProvider()
        
    if "model_call_allowed" not in signal_snapshot:
        raise ValueError("Missing model_call_allowed in signal_snapshot")
    call_allowed = bool(signal_snapshot["model_call_allowed"])
        
    if not call_allowed:
        return InertLocalModelProvider()
        
    injected_fn = route_context.get(injected_fn_key)
    if injected_fn is not None:
        return InjectedLocalModelProvider(injected_fn)
        
    provider_type = signal_snapshot.get("executor_provider")
    model_name = signal_snapshot.get("executor_model")
    
    if not provider_type or not model_name:
        raise ValueError("Missing executor_provider or executor_model in signal_snapshot")
        
    provider_type = provider_type.lower()
    model_name = model_name.strip()
    
    if provider_type == "ollama" and model_name:
        return OllamaLocalModelProvider()
        
    return InertLocalModelProvider()



def compute_patch_lifecycle_state(
    pipeline_final_patch_len: int,
    pipeline_result_projected: bool,
    candidate_isolation_attempted: bool,
    isolated_apply_status: str,
    hash_match: bool,
    applied_patch_hash: str,
    selected_candidate_hash: str,
    verifier_result: str,
    solved: bool,
) -> str:
    """Derive mutually exclusive patch lifecycle state from existing execution results.
    
    Must not trigger execution, invoke provider, invoke verifier, or invoke isolated apply.
    Fails closed on missing data.
    """
    if pipeline_final_patch_len == 0:
        return "patch_absent"

    if not pipeline_result_projected:
        return "patch_present_not_projected"

    if not candidate_isolation_attempted:
        return "patch_projected_not_isolated"

    if isolated_apply_status != "applied":
        return "isolation_attempted_apply_failed"

    if not hash_match:
        return "isolation_applied_hash_mismatch"

    if verifier_result != "pass" or not solved:
        return "isolation_applied_hash_match_verifier_failed"

    if not applied_patch_hash or not selected_candidate_hash:
        return "isolation_applied_hash_mismatch"

    if applied_patch_hash != selected_candidate_hash:
        return "isolation_applied_hash_mismatch"

    return "verifier_passed"


def compute_failure_class(
    output_len: int,
    provider_error: str,
    failure_reason: str,
    parse_error_kind: str,
    patch_lifecycle_state: str,
    verifier_result: str,
    solved: bool,
    contains_markdown_fence: bool,
    pipeline_failure_reason: str,
) -> tuple[str, str]:
    """Deterministic failure classifier from existing execution metadata.
    
    Returns (failure_class, unknown_reason).
    Classification only — must not parse/transform model output or change execution.
    """
    _reason = failure_reason or pipeline_failure_reason or ""

    # Priority 1: provider error
    if provider_error and provider_error.strip():
        return "provider_error", ""

    # Priority 2: empty response
    if output_len == 0:
        return "empty_response", ""

    # Priority 3: pipeline failure reasons (deterministic from existing telemetry)
    upper_reason = _reason.upper()
    upper_parse = (parse_error_kind or "").upper()

    if "NO_BLOCKS_FOUND" in upper_reason:
        return "no_blocks_found", ""
    if "SEARCH_MISMATCH" in upper_reason:
        return "search_mismatch", ""
    if "REPLACE_SYNTAX_ERROR" in upper_reason or "SYNTAX_ERROR" in upper_reason:
        return "replace_syntax_error", ""

    # Priority 4: fenced output
    if "REPLACEMENT_MARKDOWN_FENCE" in upper_parse or contains_markdown_fence:
        return "fenced_output", ""

    # Priority 5: refusal
    if "REFUSAL" in upper_parse or "REFUSAL" in upper_reason:
        return "refusal", ""

    # Priority 6: patch lifecycle states
    if patch_lifecycle_state == "isolation_attempted_apply_failed":
        return "patch_apply_failed", ""
    if patch_lifecycle_state == "isolation_applied_hash_mismatch":
        return "hash_mismatch", ""
    if patch_lifecycle_state == "isolation_applied_hash_match_verifier_failed":
        return "verification_failed", ""

    # Priority 7: verifier passed
    if verifier_result == "pass" and solved:
        return "verifier_passed", ""

    # Priority 8: verifier failed with patch present (semantic wrong patch)
    if verifier_result == "fail" and patch_lifecycle_state not in ("patch_absent", ""):
        return "semantic_wrong_patch", ""

    # Fallback: unknown with reason
    unknown_reason = ""
    if output_len > 0:
        unknown_reason = f"output_len={output_len}"
        if _reason:
            unknown_reason += f" pipeline_failure_reason={_reason}"
        if upper_parse:
            unknown_reason += f" parse_error_kind={parse_error_kind}"
    return "unknown_with_reason", unknown_reason


def compute_verifier_failure_evidence(
    verifier_result: str,
    verifier_error: str,
    exit_code: int | None,
    stdout_tail: str,
    stderr_tail: str,
    verifier_command: tuple[str, ...],
    failure_class: str,
    patch_lifecycle_state: str,
) -> dict[str, str | bool]:
    """Capture bounded verifier failure evidence for downstream semantic retry.
    
    Must not change verifier behavior, trigger retry, alter patch content,
    or alter candidate isolation. Evidence capture only.
    """
    evidence_available = False
    failure_kind = ""
    stdout_excerpt = ""
    stderr_excerpt = ""
    cmd_hash = ""
    retry_ready = False

    if verifier_result == "fail":
        stdout_excerpt = (stdout_tail or "")[:1000]
        stderr_excerpt = (stderr_tail or "")[:1000]
        cmd_hash = hashlib.sha256(
            " ".join(verifier_command).encode("utf-8")
        ).hexdigest()[:16] if verifier_command else ""

        if verifier_error and "timeout" in verifier_error.lower():
            failure_kind = "timeout"
        elif exit_code is not None and exit_code != 0:
            combined = (stdout_excerpt + stderr_excerpt).lower()
            if "assert" in combined or "assertionerror" in combined or "assertion error" in combined:
                failure_kind = "assertion_failure"
            elif "traceback" in combined or "exception" in combined or "error" in combined:
                failure_kind = "exception"
            else:
                failure_kind = "nonzero_exit"
        elif not verifier_command:
            failure_kind = "missing_verifier_command"
        else:
            failure_kind = "unknown_verifier_failure"

        evidence_available = bool(stdout_excerpt or stderr_excerpt or verifier_error)

    retry_ready = (
        failure_class in ("verification_failed", "semantic_wrong_patch")
        and patch_lifecycle_state in (
            "isolation_applied_hash_match_verifier_failed",
            "isolation_applied_hash_mismatch",
        )
        and evidence_available
    )

    return {
        "verifier_failure_evidence_available": evidence_available,
        "verifier_failure_kind": failure_kind,
        "verifier_stdout_excerpt": stdout_excerpt,
        "verifier_stderr_excerpt": stderr_excerpt,
        "verifier_exit_code": exit_code if exit_code is not None else "",
        "verifier_command_hash": cmd_hash,
        "semantic_retry_evidence_ready": retry_ready,
        # C15-3B: Metadata for prompt evidence injection tracking
        "semantic_retry_verifier_evidence_injected": False,
        "semantic_retry_verifier_evidence_fields": "",
        "semantic_retry_prompt_evidence_hash": "",
    }


class LocalModelExecutor:
    @staticmethod
    def run(request: LocalModelExecutorRequest, *, provider: LocalModelProvider | None = None) -> LocalModelExecutorResponse:
        empty_hash = hashlib.sha256(b"").hexdigest()
        
        try:
            execution_topology = _resolve_execution_topology(request)
        except ValueError as e:
            return LocalModelExecutorResponse(
                invoked=False,
                local_model_called=False,
                candidate_patch="",
                candidate_hash=empty_hash,
                reasoning_summary="fail_closed_missing_topology",
                raw_model_metadata={"error": str(e)},
                provider="none",
                model_name="",
                error=str(e),
                timeout=False,
                evidence_refs=request.evidence_refs,
            )
        
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
            try:
                provider = build_local_model_provider_from_signal_snapshot(
                    request.route_context,
                    "candidate_generate_fn"
                )
            except ValueError as e:
                return LocalModelExecutorResponse(
                    invoked=False,
                    local_model_called=False,
                    candidate_patch="",
                    candidate_hash=empty_hash,
                    reasoning_summary="fail_closed_missing_provider_or_model",
                    raw_model_metadata={"error": str(e)},
                    provider="none",
                    model_name="",
                    error=str(e),
                    timeout=False,
                    evidence_refs=request.evidence_refs,
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
        
        # C6: Read provider_timeout_sec from signal_snapshot (planner-owned)
        _signal_snap_early = request.route_context.get("signal_snapshot", {}) if isinstance(request.route_context, dict) else {}
        provider_timeout_sec: float = float(_signal_snap_early.get("provider_timeout_sec", 120.0))

        # 7. Build capability context (shared across all topologies)
        cap_ctx = LocalModelCapabilityContext(
            task_id=request.task_id,
            source_root=request.repo_root,
            problem_statement=request.problem_statement,
            target_file=target_file,
            target_symbol=target_symbol,
            selected_capabilities=selected_caps,
            execution_topology=execution_topology,
            evidence_refs=request.evidence_refs,
            source_anchor={"present": source_anchor_present, "source": source_anchor_source, "hash": source_anchor_hash},
            failure_feedback=failure_feedback_text,
            verifier_command=tuple(request.route_context.get("verifier_command", []) or []),
            candidate_pool=[],
            route_context=request.route_context,
            local_model_metadata={},
            provider=provider,
        )

        # 8. Handle Execution Topology Branching
        if execution_topology == "local_committee_only":
            signal_snapshot = request.route_context.get("signal_snapshot", {}) if isinstance(request.route_context, dict) else {}
            protocol_mode = signal_snapshot["protocol_mode"]
            
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
                route_context=request.route_context,
            )
            
            # Update cap_ctx with candidates for this topology
            cap_ctx.candidate_pool = candidates
            cap_ctx.problem_statement = enhanced_problem

            decision = CandidateDecisionAdapter.select_candidate(
                candidates,
                selected_capabilities=selected_caps,
                ctx=cap_ctx,
            )
            
            # Local model is called if at least one candidate wasn't blocked/abstained
            local_model_called = any(not c.abstained for c in candidates)
            
            selected_patch = decision.selected_candidate_patch
            patch_meta = {}
            retry_available = False
            retry_not_invoked_reason = ""
            mutation_allowed = bool(signal_snapshot.get("mutation_allowed", False))
            verifier_allowed = bool(signal_snapshot.get("verifier_allowed", False))
            verifier_command = tuple(request.route_context.get("verifier_command", []) or [])
            candidate_isolation_attempted = False
            candidate_isolated = False
            applied_patch_hash = ""
            hash_match = False
            isolated_apply_status = ""
            isolated_apply_error = ""
            applied_patch_hash_source = ""
            isolated_verifier_status = "not_run"
            isolated_verifier_error = ""
            hybrid_route = None
            if selected_patch.strip():
                selected_patch, patch_meta = _normalize_candidate_patch(request, locked_search, selected_patch)
                selected_hash = hashlib.sha256(selected_patch.encode("utf-8")).hexdigest() if selected_patch.strip() else empty_hash
            else:
                selected_hash = empty_hash

            # A5/B5: Wire parse failure into retry/feedback seam
            protocol_parse_failed = patch_meta.get("protocol_parse_failed", False)
            error_kind = patch_meta.get("error_kind", "")
            error_message = patch_meta.get("error_message", "")
            pipeline_retry_delegated = False
            delegated_retry_failure_reason = ""
            delegated_retry_final_patch_len = 0
            delegated_retry_output_class = ""
            delegated_retry_parser_error_kind = ""
            delegated_retry_status = ""
            delegated_retry_output_excerpt = ""
            if protocol_parse_failed:
                try:
                    from nexus.services.local_heal.failure_feedback_builder import build_failure_feedback
                    fence_feedback = build_failure_feedback(
                        task_id=request.task_id,
                        failure_class=error_kind or "PROTOCOL_PARSE_FAILED",
                        target_file=request.target_file,
                        target_symbol=target_symbol,
                        locked_search=locked_search,
                        previous_block_reason=error_kind or "protocol_parse_failed",
                        verifier_status="fail",
                    )
                    retry_available = True

                    # B5: Delegate retry to pipeline/orchestrator
                    if error_kind in {"REPLACEMENT_MARKDOWN_FENCE", "REPLACEMENT_PROSE_CONTAMINATION"} and provider is not None:
                        try:
                            from nexus.services.local_heal.pipeline import HealPipeline, HealContext as LegacyHealContext
                            from nexus.services.local_heal.corrector import SelfCorrector
                            from nexus.services.local_heal.errors import PatchError, PatchErrorKind
                            from pathlib import Path as _Path

                            def _provider_generate(system_prompt_or_req, user_prompt=None, **kwargs):
                                from nexus.services.local_heal.local_model_provider import LocalModelProviderRequest
                                if user_prompt is not None:
                                    prompt = (
                                        f"[SYSTEM]\n{system_prompt_or_req}\n\n"
                                        f"[USER]\n{user_prompt}"
                                    )
                                    model_name = kwargs.get("model", "")
                                else:
                                    prompt = getattr(system_prompt_or_req, "prompt", "") or str(system_prompt_or_req)
                                    model_name = getattr(system_prompt_or_req, "model_name", "") or kwargs.get("model", "")
                                prov_req = LocalModelProviderRequest(
                                    task_id=request.task_id,
                                    prompt=prompt,
                                    evidence_refs=request.evidence_refs,
                                    model_name=model_name,
                                    timeout_sec=provider_timeout_sec,
                                )
                                prov_resp = provider.generate(prov_req)
                                return prov_resp.output_text or ""

                            pipeline = HealPipeline(ollama_generate_fn=_provider_generate)
                            route_ctx = request.route_context if isinstance(request.route_context, dict) else {}
                            route_ctx = dict(route_ctx)
                            route_ctx.setdefault("target_file", request.target_file)
                            route_ctx.setdefault("target_symbol", target_symbol)
                            repro_script = str(route_ctx.get("repro_script", "") or "")
                            python_executable = str(route_ctx.get("python_executable", "") or "")
                            retry_kind = getattr(PatchErrorKind, error_kind, PatchErrorKind.NO_BLOCKS_FOUND)
                            retry_prompt = SelfCorrector().build_retry_prompt(
                                original_user_prompt=request.problem_statement,
                                error=PatchError(kind=retry_kind, message=error_message or error_kind),
                                targeted_files=request.target_file,
                            )
                            heal_ctx = LegacyHealContext(
                                instance_id=request.task_id,
                                repo_dir=_Path(request.repo_root),
                                problem_statement=request.problem_statement,
                                user_prompt=retry_prompt,
                                attempt=2,
                                repro_script=repro_script,
                                skip_reproduction=not bool(repro_script),
                                failure_reason=error_kind,
                                route_context=route_ctx,
                                python_executable=python_executable,
                                max_tries=2,
                            )
                            result_ctx = pipeline.run(heal_ctx)
                            delegated_retry_failure_reason = str(getattr(result_ctx, "failure_reason", "") or "")
                            delegated_retry_final_patch_len = len(getattr(result_ctx, "final_patch", "") or "")
                            retry_model_decisions = list(getattr(result_ctx, "model_decisions", []) or [])
                            patch_retry_decisions = [
                                d for d in retry_model_decisions
                                if isinstance(d, dict) and d.get("phase") == "patch"
                            ]
                            if patch_retry_decisions:
                                last_retry = patch_retry_decisions[-1]
                                delegated_retry_output_class = str(last_retry.get("output_class", "") or "")
                                delegated_retry_parser_error_kind = str(last_retry.get("parser_error_kind", "") or "")
                                delegated_retry_status = str(last_retry.get("status", "") or "")
                                delegated_retry_output_excerpt = str(last_retry.get("output_excerpt", "") or "")[:500]
                            if getattr(result_ctx, "final_patch", ""):
                                selected_patch = result_ctx.final_patch
                                selected_hash = hashlib.sha256(selected_patch.encode("utf-8")).hexdigest()
                                pipeline_retry_delegated = True
                        except Exception:
                            pipeline_retry_delegated = False

                except Exception:
                    retry_available = False
                    retry_not_invoked_reason = "feedback_builder_unavailable"

            if selected_patch.strip():
                candidate_isolation_attempted = True
                apply_receipt = run_isolated_workspace_apply(
                    IsolatedApplyRequest(
                        task_id=request.task_id,
                        source_root=request.repo_root,
                        target_file=target_file,
                        unified_diff=selected_patch,
                        selected_candidate_hash=selected_hash,
                        mutation_allowed=mutation_allowed,
                    )
                )
                isolated_apply_status = apply_receipt.patch_apply_status
                isolated_apply_error = apply_receipt.patch_apply_error
                candidate_isolated = apply_receipt.candidate_output_isolated
                applied_patch_hash = apply_receipt.applied_patch_hash
                applied_patch_hash_source = apply_receipt.applied_patch_hash_source
                hash_match = apply_receipt.selected_candidate_hash_matches_applied

                verifier_receipt = run_isolated_verifier(
                    IsolatedVerifierRequest(
                        task_id=request.task_id,
                        workspace_path=apply_receipt.workspace_path or request.repo_root,
                        verifier_command=verifier_command,
                        verifier_allowed=verifier_allowed,
                    )
                )
                isolated_verifier_status = verifier_receipt.verifier_status
                isolated_verifier_error = verifier_receipt.verifier_error

                isolation_receipt = CandidateIsolationReceipt(
                    candidate_id=decision.selected_candidate_id or f"{request.task_id}#committee-candidate",
                    selected_candidate_hash=selected_hash,
                    applied_patch_hash=applied_patch_hash,
                    selected_candidate_hash_matches_applied=hash_match,
                    candidate_output_isolated=candidate_isolated,
                    verifier_result=isolated_verifier_status,
                    evidence_refs=decision.decision_evidence_refs or request.evidence_refs,
                    local_model_called=local_model_called,
                    mutation_allowed=mutation_allowed,
                )
                hybrid_route = candidate_isolation_to_hybrid_route(isolation_receipt)

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
                "protocol_parse_failed": protocol_parse_failed,
                "protocol_parse_error_kind": error_kind,
                "retry_available": retry_available,
                "retry_not_invoked_reason": retry_not_invoked_reason,
                "pipeline_retry_delegated": pipeline_retry_delegated,
                "delegated_retry_failure_reason": delegated_retry_failure_reason,
                "delegated_retry_final_patch_len": delegated_retry_final_patch_len,
                "delegated_retry_output_class": delegated_retry_output_class,
                "delegated_retry_parser_error_kind": delegated_retry_parser_error_kind,
                "delegated_retry_status": delegated_retry_status,
                "delegated_retry_output_excerpt": delegated_retry_output_excerpt,
                "candidate_hash_empty": selected_hash == empty_hash,
                "candidate_isolation_attempted": candidate_isolation_attempted,
                "candidate_isolated": candidate_isolated,
                "candidate_output_isolated": candidate_isolated,
                "selected_candidate_hash": selected_hash if selected_hash != empty_hash else "",
                "applied_patch_hash": applied_patch_hash,
                "hash_match": hash_match,
                "selected_candidate_hash_matches_applied": hash_match,
                "isolated_apply_status": isolated_apply_status,
                "isolated_apply_error": isolated_apply_error,
                "applied_patch_hash_source": applied_patch_hash_source,
                "isolated_verifier_status": isolated_verifier_status,
                "isolated_verifier_error": isolated_verifier_error,
                "verifier_result": isolated_verifier_status,
                "mutation_allowed": mutation_allowed,
                "verifier_allowed": verifier_allowed,
            }
            if hybrid_route is not None:
                raw_meta["hybrid_route"] = hybrid_route.to_dict()
                raw_meta["route_mode"] = hybrid_route.route_mode.value
                raw_meta["authority"] = hybrid_route.authority.value
            armor_ok, armor_miss = validate_local_model_armor_metadata(raw_meta)
            raw_meta["armor_receipt_complete"] = armor_ok
            raw_meta["armor_receipt_missing_fields"] = armor_miss
            local_assist_telemetry = build_local_assist_telemetry_from_executor_meta(raw_meta)
            raw_meta["local_assist_telemetry"] = local_assist_telemetry.to_dict()
            raw_meta["solved"] = bool(
                hybrid_route is not None
                and hybrid_route.route_mode.value == "local_only_executed"
            )
            raw_meta["patch_lifecycle_state"] = compute_patch_lifecycle_state(
                pipeline_final_patch_len=len(selected_patch) if selected_patch.strip() else 0,
                pipeline_result_projected=bool(selected_patch.strip()),
                candidate_isolation_attempted=candidate_isolation_attempted,
                isolated_apply_status=isolated_apply_status,
                hash_match=hash_match,
                applied_patch_hash=applied_patch_hash,
                selected_candidate_hash=selected_hash if selected_hash != empty_hash else "",
                verifier_result=isolated_verifier_status,
                solved=raw_meta["solved"],
            )
            fc, ur = compute_failure_class(
                output_len=len(selected_patch) if selected_patch else 0,
                provider_error="",
                failure_reason="",
                parse_error_kind=error_kind,
                patch_lifecycle_state=raw_meta["patch_lifecycle_state"],
                verifier_result=isolated_verifier_status,
                solved=raw_meta["solved"],
                contains_markdown_fence=bool(patch_meta.get("outer_markdown_fence_unwrapped")),
                pipeline_failure_reason="",
            )
            raw_meta["failure_class"] = fc
            raw_meta["unknown_reason"] = ur
            vfe = compute_verifier_failure_evidence(
                verifier_result=isolated_verifier_status,
                verifier_error=isolated_verifier_error,
                exit_code=None,
                stdout_tail="",
                stderr_tail="",
                verifier_command=verifier_command,
                failure_class=fc,
                patch_lifecycle_state=raw_meta["patch_lifecycle_state"],
            )
            raw_meta.update(vfe)
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

            original_target_content = None
            original_target_exists = False
            original_target_path = ""
            if request.repo_root and target_file:
                original_target_path = os.path.join(request.repo_root, target_file)
                if os.path.exists(original_target_path):
                    original_target_exists = True
                    with open(original_target_path, "r", encoding="utf-8") as f:
                        original_target_content = f.read()

            # Execute repair_loop (localheal pipeline bridge)
            repair_exec = LocalHealPipelineCapabilityExecutor().execute(cap_ctx)

            # Execute ddtree/autoreason/gates for this topology
            ddtree_exec = DDTreeLocalExecutor().execute(cap_ctx)
            autoreason_exec = AutoreasonLocalExecutor().execute(cap_ctx)
            artifact_exec = ArtifactGateLocalExecutor().execute(cap_ctx)
            claim_exec = ClaimGateLocalExecutor().execute(cap_ctx)
            delivery_exec = DeliveryGateLocalExecutor().execute(cap_ctx)

            # B3: Check if pipeline produced a result
            pipeline_final_patch = repair_exec.telemetries.get("pipeline_final_patch", "")
            pipeline_solve_eligible = repair_exec.telemetries.get("pipeline_solve_eligible", False)
            pipeline_failure_reason = repair_exec.telemetries.get("pipeline_failure_reason", "")
            signal_snapshot = request.route_context.get("signal_snapshot", {}) if isinstance(request.route_context, dict) else {}
            mutation_allowed = bool(signal_snapshot.get("mutation_allowed", False))
            verifier_allowed = bool(signal_snapshot.get("verifier_allowed", False))
            verifier_command = tuple(request.route_context.get("verifier_command", []) or [])

            pipeline_final_patch_len = len(pipeline_final_patch) if pipeline_final_patch else 0
            pipeline_result_projected = False
            candidate_isolation_attempted = False
            candidate_isolated = False
            selected_candidate_hash = ""
            applied_patch_hash = ""
            hash_match = False
            candidate_patch = ""
            candidate_hash = empty_hash
            patch_meta = {}
            isolated_apply_status = ""
            isolated_apply_error = ""
            applied_patch_hash_source = ""
            isolated_verifier_status = "not_run"
            isolated_verifier_error = ""
            hybrid_route = None
            candidate_hash_empty = (candidate_hash == empty_hash)

            if pipeline_final_patch and pipeline_final_patch.strip():
                candidate_patch, patch_meta = _project_pipeline_patch_to_target_file(
                    pipeline_final_patch,
                    target_file,
                )
                pipeline_result_projected = True
                if candidate_patch.strip():
                    candidate_hash = hashlib.sha256(candidate_patch.encode("utf-8")).hexdigest()
                    candidate_isolation_attempted = True

                if candidate_isolation_attempted and original_target_path:
                    if original_target_exists:
                        os.makedirs(os.path.dirname(original_target_path), exist_ok=True)
                        with open(original_target_path, "w", encoding="utf-8") as f:
                            f.write(original_target_content or "")
                    elif os.path.exists(original_target_path):
                        os.remove(original_target_path)

                if candidate_isolation_attempted:
                    apply_receipt = run_isolated_workspace_apply(
                        IsolatedApplyRequest(
                            task_id=request.task_id,
                            source_root=request.repo_root,
                            target_file=target_file,
                            unified_diff=candidate_patch,
                            selected_candidate_hash=candidate_hash,
                            mutation_allowed=mutation_allowed,
                        )
                    )
                    isolated_apply_status = apply_receipt.patch_apply_status
                    isolated_apply_error = apply_receipt.patch_apply_error
                    candidate_isolated = apply_receipt.candidate_output_isolated
                    selected_candidate_hash = candidate_hash
                    applied_patch_hash = apply_receipt.applied_patch_hash
                    applied_patch_hash_source = apply_receipt.applied_patch_hash_source
                    hash_match = apply_receipt.selected_candidate_hash_matches_applied

                    verifier_receipt = run_isolated_verifier(
                        IsolatedVerifierRequest(
                            task_id=request.task_id,
                            workspace_path=apply_receipt.workspace_path or request.repo_root,
                            verifier_command=verifier_command,
                            verifier_allowed=verifier_allowed,
                        )
                    )
                    isolated_verifier_status = verifier_receipt.verifier_status
                    isolated_verifier_error = verifier_receipt.verifier_error

                    isolation_receipt = CandidateIsolationReceipt(
                        candidate_id=f"{request.task_id}#pipeline-candidate",
                        selected_candidate_hash=selected_candidate_hash,
                        applied_patch_hash=applied_patch_hash,
                        selected_candidate_hash_matches_applied=hash_match,
                        candidate_output_isolated=candidate_isolated,
                        verifier_result=isolated_verifier_status,
                        evidence_refs=request.evidence_refs,
                        local_model_called=bool(
                            repair_exec.telemetries.get("model_called", False)
                            or repair_exec.telemetries.get("patch_synthesis_model_called", False)
                        ),
                        mutation_allowed=mutation_allowed,
                    )
                    hybrid_route = candidate_isolation_to_hybrid_route(isolation_receipt)
                    candidate_hash_empty = (candidate_hash == empty_hash)

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
                "protocol_normalization": patch_meta,
                "ddtree_invoked": ddtree_exec.invoked,
                "autoreason_invoked": autoreason_exec.invoked,
                "artifact_gate_invoked": artifact_exec.invoked,
                "claim_gate_invoked": claim_exec.invoked,
                "delivery_gate_invoked": delivery_exec.invoked,
                **{k: v for k, v in repair_exec.telemetries.items()},
                "gate_results": {
                    "artifact_gate": artifact_exec.to_receipt_dict(),
                    "claim_gate": claim_exec.to_receipt_dict(),
                    "delivery_gate": delivery_exec.to_receipt_dict(),
                },
                "pipeline_result_projected": pipeline_result_projected,
                "pipeline_final_patch": pipeline_final_patch,
                "pipeline_final_patch_len": pipeline_final_patch_len,
                "pipeline_solve_eligible": pipeline_solve_eligible,
                "pipeline_failure_reason": pipeline_failure_reason,
                "localheal_pipeline_run_called": repair_exec.telemetries.get("localheal_pipeline_run_called", False),
                "localheal_pipeline_run_success": repair_exec.telemetries.get("localheal_pipeline_run_success", False),
                "orchestrator_run_reachable": repair_exec.telemetries.get("orchestrator_run_reachable", False),
                "candidate_hash_empty": candidate_hash_empty,
                "candidate_isolation_attempted": candidate_isolation_attempted,
                "candidate_isolated": candidate_isolated,
                "candidate_output_isolated": candidate_isolated,
                "selected_candidate_hash": selected_candidate_hash,
                "applied_patch_hash": applied_patch_hash,
                "hash_match": hash_match,
                "selected_candidate_hash_matches_applied": hash_match,
                "isolated_apply_status": isolated_apply_status,
                "isolated_apply_error": isolated_apply_error,
                "applied_patch_hash_source": applied_patch_hash_source,
                "isolated_verifier_status": isolated_verifier_status,
                "isolated_verifier_error": isolated_verifier_error,
                "verifier_result": isolated_verifier_status,
                "mutation_allowed": mutation_allowed,
                "verifier_allowed": verifier_allowed,
            }
            if hybrid_route is not None:
                raw_meta["hybrid_route"] = hybrid_route.to_dict()
                raw_meta["route_mode"] = hybrid_route.route_mode.value
                raw_meta["authority"] = hybrid_route.authority.value
            raw_meta["ddtree_result"] = ddtree_exec.to_receipt_dict()
            raw_meta["autoreason_result"] = autoreason_exec.to_receipt_dict()
            armor_ok, armor_miss = validate_local_model_armor_metadata(raw_meta)
            raw_meta["armor_receipt_complete"] = armor_ok
            raw_meta["armor_receipt_missing_fields"] = armor_miss

            provider_name = "ollama" if isinstance(provider, OllamaLocalModelProvider) else "injected"
            local_assist_telemetry = build_local_assist_telemetry_from_executor_meta(raw_meta)
            raw_meta["local_assist_telemetry"] = local_assist_telemetry.to_dict()

            raw_meta["solved"] = bool(
                pipeline_solve_eligible
                and hybrid_route is not None
                and hybrid_route.route_mode.value == "local_only_executed"
            )

            # C14: Downstream receipt truth — distinguish execution shell from model output
            raw_meta["executor_shell_reached"] = True
            raw_meta["actual_model_output_len"] = repair_exec.telemetries.get("patch_synthesis_output_len", 0)
            raw_meta["actual_model_name_used"] = repair_exec.telemetries.get("patch_synthesis_model_name", "")
            raw_meta["actual_provider_invoked"] = repair_exec.telemetries.get("provider_invoked", False)
            raw_meta["actual_model_called"] = repair_exec.telemetries.get("patch_synthesis_model_called", False)
            # Why model call didn't produce patch (if applicable)
            no_reason = ""
            if not pipeline_final_patch:
                if not raw_meta["actual_model_called"]:
                    no_reason = "model_not_called"
                elif raw_meta["actual_model_output_len"] == 0:
                    no_reason = "model_empty_output"
                elif "SEARCH_MISMATCH" in pipeline_failure_reason:
                    no_reason = "search_mismatch"
                elif "NO_BLOCKS_FOUND" in pipeline_failure_reason:
                    no_reason = "no_blocks_found"
                elif "REFUSAL" in pipeline_failure_reason:
                    no_reason = "model_refusal"
                elif "REPLACEMENT_MARKDOWN_FENCE" in pipeline_failure_reason:
                    no_reason = "fenced_output"
                else:
                    no_reason = "protocol_adherence_failure"
            raw_meta["no_model_call_reason"] = no_reason
            raw_meta["no_patch_reason"] = no_reason

            raw_meta["patch_lifecycle_state"] = compute_patch_lifecycle_state(
                pipeline_final_patch_len=pipeline_final_patch_len,
                pipeline_result_projected=pipeline_result_projected,
                candidate_isolation_attempted=candidate_isolation_attempted,
                isolated_apply_status=isolated_apply_status,
                hash_match=hash_match,
                applied_patch_hash=applied_patch_hash,
                selected_candidate_hash=selected_candidate_hash,
                verifier_result=isolated_verifier_status,
                solved=raw_meta["solved"],
            )
            fc, ur = compute_failure_class(
                output_len=raw_meta.get("actual_model_output_len", 0),
                provider_error=repair_exec.telemetries.get("patch_synthesis_provider_error", ""),
                failure_reason=pipeline_failure_reason,
                parse_error_kind=repair_exec.telemetries.get("output_class", ""),
                patch_lifecycle_state=raw_meta["patch_lifecycle_state"],
                verifier_result=isolated_verifier_status,
                solved=raw_meta["solved"],
                contains_markdown_fence=bool(repair_exec.telemetries.get("contains_markdown_fence", False)),
                pipeline_failure_reason=pipeline_failure_reason,
            )
            raw_meta["failure_class"] = fc
            raw_meta["unknown_reason"] = ur
            vfe = compute_verifier_failure_evidence(
                verifier_result=isolated_verifier_status,
                verifier_error=isolated_verifier_error,
                exit_code=None,
                stdout_tail="",
                stderr_tail="",
                verifier_command=verifier_command,
                failure_class=fc,
                patch_lifecycle_state=raw_meta["patch_lifecycle_state"],
            )
            raw_meta.update(vfe)

            return LocalModelExecutorResponse(
                invoked=True,
                local_model_called=True,
                candidate_patch=candidate_patch,
                candidate_hash=candidate_hash,
                reasoning_summary="pipeline_result" if pipeline_result_projected else "pipeline_failed_empty",
                raw_model_metadata=raw_meta,
                provider=provider_name,
                model_name=repair_exec.telemetries.get("patch_synthesis_model_name", ""),
                error="",
                timeout=False,
                evidence_refs=request.evidence_refs,
            )


        # 9. Generate Candidate Patch for single_local_model
        signal_snapshot = request.route_context.get("signal_snapshot", {}) if isinstance(request.route_context, dict) else {}
        protocol_mode = signal_snapshot["protocol_mode"]
        
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

        model_name = signal_snapshot["executor_model"]
        prov_req = LocalModelProviderRequest(
            task_id=request.task_id,
            prompt=explicit_prompt,
            evidence_refs=request.evidence_refs,
            model_name=model_name,
            timeout_sec=provider_timeout_sec,
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
            "timed_out": prov_resp.timed_out,
            "requested_timeout_sec": prov_resp.requested_timeout_sec,
            "effective_timeout_sec": prov_resp.effective_timeout_sec,
            "elapsed_sec": prov_resp.elapsed_sec,
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
        local_assist_telemetry = build_local_assist_telemetry_from_executor_meta(raw_meta)
        raw_meta["local_assist_telemetry"] = local_assist_telemetry.to_dict()
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

    candidate_patch, outer_unwrap_meta = _unwrap_outer_markdown_fence(candidate_patch)
    candidate_patch, replace_unwrap_meta = _unwrap_markdown_fence_inside_replace_block(candidate_patch)
    unwrap_meta = {
        "normalized": bool(
            outer_unwrap_meta.get("normalized", False)
            or replace_unwrap_meta.get("normalized", False)
        ),
        **outer_unwrap_meta,
        **replace_unwrap_meta,
    }
    
    # 1. Already standard unified diff — pass through
    if "--- a/" in candidate_patch and "+++ b/" in candidate_patch and "<<<<<<< REPLACE" not in candidate_patch:
        return candidate_patch, {
            "protocol_used": "passthrough",
            "normalized": bool(unwrap_meta.get("normalized", False)),
            **unwrap_meta,
        }
    
    # 2. Use SolidSearchReplaceProtocol to parse REPLACE block
    from nexus.services.local_heal.protocol import SolidSearchReplaceProtocol, PatchError
    
    protocol = SolidSearchReplaceProtocol()
    anchor_text = locked_search if locked_search.strip() else None
    
    result = protocol.parse(candidate_patch, anchor_text=anchor_text, protocol_mode="anchored_edit")
    
    # 3. Handle parse error — fail closed
    if isinstance(result, PatchError):
        return "", {
            "protocol_parse_failed": True,
            "error_kind": result.kind.name if hasattr(result.kind, "name") else str(result.kind),
            "error_message": result.message,
            **unwrap_meta,
        }
    
    # 4. Got PatchIntent(s) — extract replacement from first intent
    if not result:
        return "", {"protocol_parse_failed": True, "error": "no_intents", **unwrap_meta}
    
    intent = result[0]
    replacement = intent.replace
    
    if not replacement.strip():
        return "", {"protocol_parse_failed": True, "error": "empty_replacement", **unwrap_meta}
    
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
    return normalized, {
        "protocol_used": "solid_search_replace",
        "normalized": True,
        **unwrap_meta,
    }
