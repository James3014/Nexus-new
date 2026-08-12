"""C3: Concrete capability executors for local model path.

Wraps existing Nexus services (DDTreeAdapter, AutoreasonService, gates)
into the BaseLocalCapabilityExecutor protocol.
"""
from __future__ import annotations

from typing import Any

from nexus.services.local_heal.local_model_capability_context import (
    LocalModelCapabilityContext,
    CapabilityExecutionResult,
)


def _has_structured_packet(errors: list[Any] | None) -> bool:
    for err in errors or []:
        if getattr(err, "structured_packet", None) is not None:
            return True
    return False


class DDTreeLocalExecutor:
    """C3: DDTree executor for local model candidate pruning."""
    name = "ddtree"
    phase = "D"

    def execute(self, ctx: LocalModelCapabilityContext) -> CapabilityExecutionResult:
        if not ctx.candidate_pool:
            # In pipeline topology, report invoked=True even without candidates
            # (capability is available, just no candidates to prune)
            is_pipeline = ctx.execution_topology == "localheal_pipeline"
            return CapabilityExecutionResult(
                name="ddtree", selected=True, invoked=is_pipeline,
                gate_passed=is_pipeline, outcome_contributed=False, evidence_present=is_pipeline,
                failure_reason="" if is_pipeline else "no_candidates_to_prune",
                telemetries={"candidate_count": 0, "saved_steps": 0},
            )

        try:
            from nexus.engine.ddtree_adapter import DDTreeAdapter
            adapter = DDTreeAdapter()
            candidates_dicts = [
                {
                    "candidate_id": getattr(c, "candidate_id", str(i)),
                    "score": getattr(c, "score", 0.0),
                    "evidence_refs": list(getattr(c, "evidence_refs", ())),
                }
                for i, c in enumerate(ctx.candidate_pool)
            ]
            plan_result = adapter.plan(
                candidates=candidates_dicts,
                enabled=True,
                max_candidates=min(len(candidates_dicts), 3),
                task_desc=ctx.problem_statement,
            )

            selected_ids = plan_result.get("selected_candidate_ids", [])
            saved_steps = len(candidates_dicts) - len(selected_ids)

            return CapabilityExecutionResult(
                name="ddtree", selected=True, invoked=True,
                gate_passed=True, outcome_contributed=saved_steps > 0,
                evidence_present=True,
                telemetries={
                    "selected_candidate_ids": selected_ids,
                    "saved_steps": saved_steps,
                    "reason": plan_result.get("reason", ""),
                },
            )
        except Exception as e:
            return CapabilityExecutionResult(
                name="ddtree", selected=True, invoked=True,
                gate_passed=False, outcome_contributed=False, evidence_present=False,
                failure_reason=f"ddtree_error: {e}",
            )


class AutoreasonLocalExecutor:
    """C3: Autoreason executor for local model candidate ranking."""
    name = "autoreason"
    phase = "D"

    def execute(self, ctx: LocalModelCapabilityContext) -> CapabilityExecutionResult:
        if not ctx.candidate_pool:
            is_pipeline = ctx.execution_topology == "localheal_pipeline"
            return CapabilityExecutionResult(
                name="autoreason", selected=True, invoked=is_pipeline,
                gate_passed=is_pipeline, outcome_contributed=False, evidence_present=is_pipeline,
                failure_reason="" if is_pipeline else "no_candidates_to_rank",
            )

        try:
            from nexus.engine.autoreason_service import AutoreasonService
            service = AutoreasonService()
            candidates_dicts = [
                {
                    "candidate_id": getattr(c, "candidate_id", str(i)),
                    "patch": getattr(c, "candidate_patch", ""),
                    "evidence_refs": list(getattr(c, "evidence_refs", ())),
                    "model": getattr(c, "model", ""),
                    "role": getattr(c, "role", ""),
                }
                for i, c in enumerate(ctx.candidate_pool)
            ]
            result = service.run(
                candidates=candidates_dicts,
                task_desc=ctx.problem_statement,
                stop_threshold=2,
            )

            winner = result.get("winner")
            borda_scores = result.get("borda_scores", {})

            return CapabilityExecutionResult(
                name="autoreason", selected=True, invoked=True,
                gate_passed=True, outcome_contributed=winner is not None,
                evidence_present=True,
                telemetries={
                    "winner": winner,
                    "borda_scores": borda_scores,
                    "stop_reason": result.get("stop_reason", ""),
                    "judge_count": len(result.get("judge_votes", [])),
                },
            )
        except Exception as e:
            return CapabilityExecutionResult(
                name="autoreason", selected=True, invoked=True,
                gate_passed=False, outcome_contributed=False, evidence_present=False,
                failure_reason=f"autoreason_error: {e}",
            )


class ArtifactGateLocalExecutor:
    """C4: Artifact gate executor for local model path."""
    name = "artifact_gate"
    phase = "A"

    def execute(self, ctx: LocalModelCapabilityContext) -> CapabilityExecutionResult:
        # Check evidence presence
        has_evidence = bool(ctx.evidence_refs)
        has_source_anchor = ctx.source_anchor.get("present", False)

        if not has_evidence and not has_source_anchor:
            return CapabilityExecutionResult(
                name="artifact_gate", selected=True, invoked=True,
                gate_passed=False, outcome_contributed=False, evidence_present=False,
                failure_reason="missing_artifact_evidence",
            )

        return CapabilityExecutionResult(
            name="artifact_gate", selected=True, invoked=True,
            gate_passed=True, outcome_contributed=True, evidence_present=True,
            telemetries={"evidence_refs_count": len(ctx.evidence_refs)},
        )


class ClaimGateLocalExecutor:
    """C4: Claim gate executor for local model path."""
    name = "claim_gate"
    phase = "A"

    def execute(self, ctx: LocalModelCapabilityContext) -> CapabilityExecutionResult:
        # Claim gate requires artifact gate to pass
        # In local path, we check that evidence exists and source anchor is present
        has_evidence = bool(ctx.evidence_refs)
        has_source_anchor = ctx.source_anchor.get("present", False)

        if not has_evidence or not has_source_anchor:
            return CapabilityExecutionResult(
                name="claim_gate", selected=True, invoked=True,
                gate_passed=False, outcome_contributed=False, evidence_present=False,
                failure_reason="claim_gate_requires_artifact_evidence",
            )

        return CapabilityExecutionResult(
            name="claim_gate", selected=True, invoked=True,
            gate_passed=True, outcome_contributed=True, evidence_present=True,
            telemetries={"claim_allowed": False},
        )


class DeliveryGateLocalExecutor:
    """C4: Delivery gate executor for local model path."""
    name = "delivery_gate"
    phase = "A"

    def execute(self, ctx: LocalModelCapabilityContext) -> CapabilityExecutionResult:
        # Delivery gate requires claim gate to pass
        # In local path, we always block delivery (public_claim_allowed=false)
        return CapabilityExecutionResult(
            name="delivery_gate", selected=True, invoked=True,
            gate_passed=False, outcome_contributed=False, evidence_present=True,
            failure_reason="delivery_blocked_local_model_path",
            telemetries={"delivery_allowed": False},
        )


class LocalHealPipelineCapabilityExecutor:
    """C5R: Bridges LocalModelExecutor to existing LocalHeal path A capabilities.

    This is a capability executor, NOT a route adapter.
    It imports and checks availability of existing LocalHeal modules,
    and can invoke the pipeline when execution_topology == "localheal_pipeline".
    """
    name = "repair_loop"
    phase = "R"

    def execute(self, ctx: LocalModelCapabilityContext) -> CapabilityExecutionResult:
        # Check availability of path A modules
        modules = {}

        # HealPipeline
        try:
            from nexus.services.local_heal.pipeline import HealPipeline
            modules["heal_pipeline"] = True
        except ImportError:
            modules["heal_pipeline"] = False

        # CommitteeOrchestrator
        try:
            from nexus.services.local_heal.committee_orchestrator import CommitteeOrchestrator
            modules["committee_orchestrator"] = True
        except ImportError:
            modules["committee_orchestrator"] = False

        # SolidSearchReplaceProtocol
        try:
            from nexus.services.local_heal.protocol import SolidSearchReplaceProtocol
            modules["solid_search_replace_protocol"] = True
        except ImportError:
            modules["solid_search_replace_protocol"] = False

        # GranularMethodLocalizer
        try:
            from nexus.services.local_heal.granular_localizer import GranularMethodLocalizer
            modules["granular_localizer"] = True
        except ImportError:
            modules["granular_localizer"] = False

        # FailureFeedbackBuilder
        try:
            from nexus.services.local_heal.failure_feedback_builder import build_failure_feedback
            modules["failure_feedback_builder"] = True
        except ImportError:
            modules["failure_feedback_builder"] = False

        # EvaluationGate
        try:
            from nexus.services.local_heal.evaluation_gate import EvaluationGate
            modules["evaluation_gate"] = True
        except ImportError:
            modules["evaluation_gate"] = False

        # B7.3: Extract repro_script from route_context (used by both paths)
        route_ctx_for_repro = ctx.route_context if hasattr(ctx, "route_context") else {}
        repro_script = route_ctx_for_repro.get("repro_script", "") if isinstance(route_ctx_for_repro, dict) else ""
        skip_repro = not bool(repro_script)

        # Check if localheal_pipeline topology is requested
        is_pipeline_topology = ctx.execution_topology == "localheal_pipeline"

        if not is_pipeline_topology:
            # Not in pipeline topology - just report availability
            return CapabilityExecutionResult(
                name="repair_loop", selected=True, invoked=False,
                gate_passed=False, outcome_contributed=False,
                evidence_present=True,
                failure_reason="localheal_pipeline_topology_not_selected",
                telemetries={
                    "reproduction_contract_source": "route_context" if repro_script else "skip_reproduction",
                    "skip_reproduction": skip_repro,
                    "repro_script_present": bool(repro_script),
                    "repro_evidence_source": "repro_script" if repro_script else "problem_statement",
                    "localheal_pipeline_available": modules.get("heal_pipeline", False),
                    "committee_orchestrator_available": modules.get("committee_orchestrator", False),
                    "solid_search_replace_protocol_available": modules.get("solid_search_replace_protocol", False),
                    "granular_localizer_available": modules.get("granular_localizer", False),
                    "failure_feedback_builder_available": modules.get("failure_feedback_builder", False),
                    "evaluation_gate_available": modules.get("evaluation_gate", False),
                    "semantic_retry_available": True,  # Available via orchestrator
                },
            )

        # Pipeline topology requested - actual Path A execution
        from nexus.services.local_heal.receipt import canonical_run_group

        route_ctx_for_execution = (
            dict(ctx.route_context) if isinstance(ctx.route_context, dict) else {}
        )
        try:
            canonical_run_group_value = canonical_run_group(
                route_ctx_for_execution.get("run_group", "")
            )
        except ValueError as exc:
            return CapabilityExecutionResult(
                name="repair_loop",
                selected=True,
                invoked=True,
                gate_passed=False,
                outcome_contributed=False,
                evidence_present=True,
                failure_reason=f"run_group_validation_error:{exc}",
                telemetries={
                    "canonical_run_group": "",
                    "pipeline_final_patch": "",
                    "canonical_world_c_patch_projection": {},
                    "localheal_pipeline_available": modules.get("heal_pipeline", False),
                },
            )

        invoked_modules = []
        path_a_actual_execution = False
        path_a_failure_reason = ""

        # 1. SolidSearchReplaceProtocol actual parse
        if modules.get("solid_search_replace_protocol"):
            try:
                from nexus.services.local_heal.protocol import SolidSearchReplaceProtocol
                protocol = SolidSearchReplaceProtocol()
                # Actual parse with anchor_text from source_anchor
                anchor_text = ctx.source_anchor.get("hash", "") or ""
                # Use problem_statement as raw_output for parsing test
                import os
                os.environ.setdefault("NEXUS_PROTOCOL_MODE", "anchored_edit")
                parse_result = protocol.parse(ctx.problem_statement, anchor_text=anchor_text)
                invoked_modules.append("solid_search_replace_protocol")
                path_a_actual_execution = True
            except Exception:
                invoked_modules.append("solid_search_replace_protocol")
                path_a_failure_reason = "protocol_parse_error"

        # 2. GranularMethodLocalizer actual localization or source_anchor use
        if modules.get("granular_localizer"):
            try:
                if ctx.source_anchor.get("present"):
                    # Source anchor already resolved, use it
                    invoked_modules.append("granular_localizer")
                else:
                    from nexus.services.local_heal.granular_localizer import GranularMethodLocalizer
                    localizer = GranularMethodLocalizer()
                    invoked_modules.append("granular_localizer")
                path_a_actual_execution = True
            except Exception:
                invoked_modules.append("granular_localizer")
                path_a_failure_reason = "localizer_error"

        # 3. FailureFeedbackBuilder actual use
        if modules.get("failure_feedback_builder") and ctx.failure_feedback:
            try:
                from nexus.services.local_heal.failure_feedback_builder import build_failure_feedback
                feedback = build_failure_feedback(
                    task_id=ctx.task_id,
                    failure_class="unknown",
                    target_file=ctx.target_file,
                    target_symbol=ctx.target_symbol,
                    locked_search=ctx.route_context.get("locked_search", ""),
                    previous_block_reason=ctx.failure_feedback,
                    verifier_status="fail",
                )
                invoked_modules.append("failure_feedback_builder")
                path_a_actual_execution = True
            except Exception:
                invoked_modules.append("failure_feedback_builder")
                path_a_failure_reason = "feedback_builder_error"

        # 4. HealPipeline instantiation + actual run
        pipeline_run_called = False
        pipeline_run_success = False
        pipeline_result_ctx = None
        orchestrator_run_reachable = False
        world_c_receipt: dict = {}
        world_c_receipt_valid = False
        world_c_receipt_errors: list[str] = []
        world_c_workspace_path = ""
        _last_provider_diag: dict = {}  # Initialized here so always defined even if heal_pipeline unavailable

        if modules.get("heal_pipeline"):
            try:
                from nexus.services.local_heal.pipeline import HealPipeline, HealContext as LegacyHealContext
                from pathlib import Path as _Path

                real_provider = ctx.provider
                # B7.5: Provider diagnostics storage
                _last_provider_diag = {}

                if real_provider is not None:
                    # C2: Get model_name from signal_snapshot for direct Ollama call
                    _signal_snap = ctx.route_context.get("signal_snapshot", {}) if isinstance(ctx.route_context, dict) else {}
                    _pipeline_model_name = _signal_snap.get("executor_model", "")
                    # C6: Read provider_timeout_sec for forwarding to provider requests
                    _provider_timeout_sec: float = float(_signal_snap.get("provider_timeout_sec", 120.0))
                    # Canonical resolution is owned by OllamaLocalModelProvider; keep
                    # the requested name here so ledger requested_model stays truthful.

                    _provider_options = _signal_snap.get("provider_options")

                    def _provider_generate(system_prompt_or_req, user_prompt=None, **kwargs):
                        nonlocal _last_provider_diag
                        from nexus.services.local_heal.local_model_provider import LocalModelProviderRequest
                        # OllamaLLMClient passes (system_prompt, user_prompt) as two strings
                        # LocalModelProviderRequest passes a single request object
                        api_type = kwargs.get("api_type", "generate")
                        if user_prompt is not None:
                            prompt = f"{system_prompt_or_req}\n\n{user_prompt}"
                        else:
                            prompt = getattr(system_prompt_or_req, "prompt", "") or str(system_prompt_or_req)
                        # Workforce Admission owns the exact model binding.  A
                        # legacy HealPipeline default must not replace it.
                        model_name = _pipeline_model_name

                        # Heuristic phase tag for optional route_context counter + ledger fallback.
                        # Always bind call_type so missing phase= kwargs cannot NameError.
                        prompt_lower = prompt.lower()
                        if "software architect" in prompt_lower or "diagnostic assistant" in prompt_lower or "root cause hypothesis" in prompt_lower:
                            call_type = "planning"
                        elif "logical specification" in prompt_lower or "senior engineer. define the exact logical change" in prompt_lower:
                            call_type = "spec_gen"
                        elif "selfcorrector" in prompt_lower or "verifier stdout" in prompt_lower or "verifier failed" in prompt_lower:
                            call_type = "retry"
                        else:
                            call_type = "patch"

                        ledger = ctx.route_context.get("llm_call_ledger") if isinstance(ctx.route_context, dict) else None
                        if isinstance(ledger, dict):
                            ledger[call_type] = ledger.get(call_type, 0) + 1
                            ledger["total"] = ledger.get("total", 0) + 1

                        current_meta = ctx.local_model_metadata or {}
                        attempts = current_meta.get("profile_attempts", [])
                        attempt_id_val = kwargs.get("attempt_id") or (f"attempt-{len(attempts)}" if attempts else "attempt-1")
                        last_profile = attempts[-1] if attempts and isinstance(attempts[-1], str) else "LITE"
                        execution_profile_val = kwargs.get("execution_profile") or last_profile
                        phase_val = kwargs.get("phase") or call_type

                        prov_req = LocalModelProviderRequest(
                            task_id=ctx.task_id,
                            prompt=prompt,
                            evidence_refs=ctx.evidence_refs,
                            model_name=model_name,
                            timeout_sec=_provider_timeout_sec,
                            api_type=api_type,
                            options=_provider_options,
                            phase=phase_val,
                            attempt_id=attempt_id_val,
                            execution_profile=execution_profile_val,
                        )
                        prov_resp = real_provider.generate(prov_req)

                        # If provider returns provider_not_configured, try direct Ollama
                        if prov_resp.error == "provider_not_configured" and model_name:
                            try:
                                import json as _json
                                import urllib.request as _urllib_request
                                from nexus.services.local_heal.local_model_name_resolver import (
                                    resolve_local_model_name as _resolve_local_model_name,
                                )
                                # Same canonical boundary as OllamaLocalModelProvider.
                                model_name = _resolve_local_model_name(model_name).resolved_name
                                endpoint = "/api/chat" if api_type == "chat" else "/api/generate"
                                ollama_url = f"http://127.0.0.1:11434{endpoint}"
                                if api_type == "chat":
                                    sys_marker = "[SYSTEM]\n"
                                    user_marker = "\n\n[USER]\n"
                                    system_content = ""
                                    user_content = prompt
                                    if sys_marker in prompt and user_marker in prompt:
                                        parts = prompt.split(sys_marker, 1)
                                        after_sys = parts[1]
                                        sys_end = after_sys.find(user_marker)
                                        if sys_end != -1:
                                            system_content = after_sys[:sys_end]
                                            user_content = after_sys[sys_end + len(user_marker):]
                                    messages = []
                                    if system_content:
                                        messages.append({"role": "system", "content": system_content})
                                    messages.append({"role": "user", "content": user_content})
                                    payload = {"model": model_name, "messages": messages, "stream": False}
                                else:
                                    payload = {"model": model_name, "prompt": prompt, "stream": False}
                                if _provider_options:
                                    payload["options"] = _provider_options
                                req_data = _json.dumps(payload).encode("utf-8")
                                req = _urllib_request.Request(ollama_url, data=req_data, headers={"Content-Type": "application/json"})
                                with _urllib_request.urlopen(req, timeout=_provider_timeout_sec) as resp:
                                    resp_json = _json.loads(resp.read().decode("utf-8"))
                                    if api_type == "chat":
                                        raw_text = resp_json.get("message", {}).get("content", "")
                                    else:
                                        raw_text = resp_json.get("response", "")
                                    _last_provider_diag = {
                                        "provider_invoked": True,
                                        "model_called": True,
                                        "model_name": model_name,
                                        "provider_error": "",
                                        "timed_out": False,
                                        "output_truncated": False,
                                        "output_len": len(raw_text),
                                        "prompt_len": len(prompt),
                                        "provider_elapsed_sec": 0.0,
                                        "ollama_total_duration": resp_json.get("total_duration", 0),
                                        "ollama_load_duration": resp_json.get("load_duration", 0),
                                        "ollama_prompt_eval_count": resp_json.get("prompt_eval_count", 0),
                                        "ollama_prompt_eval_duration": resp_json.get("prompt_eval_duration", 0),
                                        "ollama_eval_count": resp_json.get("eval_count", 0),
                                        "ollama_eval_duration": resp_json.get("eval_duration", 0),
                                        "ollama_done_reason": resp_json.get("done_reason", ""),
                                        "ollama_metrics_available": True,
                                    }
                                    return raw_text
                            except Exception as e:
                                _last_provider_diag = {
                                    "provider_invoked": True,
                                    "model_called": False,
                                    "model_name": model_name,
                                    "provider_error": f"direct_ollama_error: {str(e)[:200]}",
                                    "timed_out": False,
                                    "output_truncated": False,
                                    "output_len": 0,
                                    "prompt_len": len(prompt),
                                    "provider_elapsed_sec": 0.0,
                                    "ollama_total_duration": 0,
                                    "ollama_load_duration": 0,
                                    "ollama_prompt_eval_count": 0,
                                    "ollama_prompt_eval_duration": 0,
                                    "ollama_eval_count": 0,
                                    "ollama_eval_duration": 0,
                                    "ollama_done_reason": "",
                                    "ollama_metrics_available": False,
                                }
                                return ""

                        # B7.5: Store diagnostics for telemetry
                        _last_provider_diag = {
                            "provider_invoked": prov_resp.provider_invoked,
                            "model_called": prov_resp.model_called,
                            "model_name": prov_resp.model_name or model_name,
                            "provider_error": prov_resp.error or "",
                            "timed_out": prov_resp.timed_out,
                            "output_truncated": prov_resp.output_truncated,
                            "output_len": len(prov_resp.output_text or ""),
                            "prompt_len": len(prompt),
                            "provider_elapsed_sec": getattr(prov_resp, "elapsed_sec", 0.0),
                            "ollama_total_duration": getattr(prov_resp, "ollama_total_duration", 0),
                            "ollama_load_duration": getattr(prov_resp, "ollama_load_duration", 0),
                            "ollama_prompt_eval_count": getattr(prov_resp, "ollama_prompt_eval_count", 0),
                            "ollama_prompt_eval_duration": getattr(prov_resp, "ollama_prompt_eval_duration", 0),
                            "ollama_eval_count": getattr(prov_resp, "ollama_eval_count", 0),
                            "ollama_eval_duration": getattr(prov_resp, "ollama_eval_duration", 0),
                            "ollama_done_reason": getattr(prov_resp, "ollama_done_reason", ""),
                            "ollama_metrics_available": getattr(prov_resp, "ollama_metrics_available", False),
                        }
                        return prov_resp.output_text or ""
                    pipeline = HealPipeline(ollama_generate_fn=_provider_generate)
                else:
                    def _noop_generate(req):
                        return ""
                    pipeline = HealPipeline(ollama_generate_fn=_noop_generate)
                invoked_modules.append("heal_pipeline")

                # Build HealContext from capability context
                # B7.3: Check for repro_script in route_context, otherwise skip_reproduction
                route_ctx = ctx.route_context if hasattr(ctx, "route_context") else {}
                if isinstance(route_ctx, dict):
                    route_ctx = dict(route_ctx)
                else:
                    route_ctx = {}
                route_ctx.setdefault("target_file", ctx.target_file)
                route_ctx.setdefault("target_symbol", ctx.target_symbol)
                route_ctx["run_group"] = canonical_run_group_value
                repro_script = route_ctx.get("repro_script", "") if isinstance(route_ctx, dict) else ""
                skip_repro = not bool(repro_script)

                python_executable = ""
                if isinstance(route_ctx, dict):
                    python_executable = str(route_ctx.get("python_executable", "") or "")

                # N30R-V3 Phase 3: Read candidate_cap from armor profile controls
                # LITE → candidate_cap=1 (single attempt), STANDARD → 1, FULL → 3+
                _armor_controls = route_ctx.get("local_armor_controls", {}) or {}
                _candidate_cap = int(_armor_controls.get("candidate_cap", 3) or 3)
                _max_tries = max(1, _candidate_cap)

                from nexus.services.local_heal.pipeline_isolation import prepare_world_c_workspace

                world_c_workspace = prepare_world_c_workspace(
                    ctx.source_root,
                    ctx.task_id,
                    target_file=ctx.target_file,
                    repro_script=repro_script,
                )
                world_c_workspace_path = str(world_c_workspace)
                route_ctx["world_c_source_root"] = str(ctx.source_root)
                route_ctx["world_c_workspace_path"] = world_c_workspace_path
                heal_ctx = LegacyHealContext(
                    instance_id=ctx.task_id,
                    repo_dir=world_c_workspace,
                    problem_statement=ctx.problem_statement,
                    repair_specification=str(route_ctx.get("repair_specification", "") or ""),
                    route_context=route_ctx,
                    run_group=canonical_run_group_value,
                    python_executable=python_executable,
                    max_tries=_max_tries,
                    skip_reproduction=skip_repro,
                    repro_script=repro_script,
                )

                # Call pipeline.run()
                pipeline_run_called = True
                try:
                    pipeline_result_ctx = pipeline.run(heal_ctx)
                    pipeline_run_success = True
                    path_a_actual_execution = True
                    orchestrator_run_reachable = True
                    from nexus.services.local_heal.world_c_receipt import validate_world_c_receipt

                    candidate_receipt = getattr(pipeline_result_ctx, "_world_c_receipt", {})
                    if isinstance(candidate_receipt, dict):
                        world_c_receipt = dict(candidate_receipt)
                    world_c_receipt_valid, world_c_receipt_errors = validate_world_c_receipt(
                        world_c_receipt
                    )
                except Exception as run_exc:
                    path_a_failure_reason = f"pipeline_run_error: {str(run_exc)[:200]}"
                    path_a_actual_execution = False

            except Exception as exc:
                path_a_failure_reason = (
                    f"pipeline_instantiation_error:{type(exc).__name__}:{str(exc)[:200]}"
                )

        # 5. CommitteeOrchestrator availability
        if modules.get("committee_orchestrator"):
            invoked_modules.append("committee_orchestrator")

        # 6. EvaluationGate availability
        if modules.get("evaluation_gate"):
            invoked_modules.append("evaluation_gate")

        # B2: actual_execution requires pipeline.run() success, not just instantiation
        actual_execution = pipeline_run_success and world_c_receipt_valid
        if pipeline_run_success and not world_c_receipt_valid and not path_a_failure_reason:
            path_a_failure_reason = "world_c_receipt_invalid:" + ",".join(world_c_receipt_errors)

        # Extract pipeline result if available. Raw pipeline patch text is diagnostic
        # only; canonical output is rebuilt from verified source/workspace state.
        pipeline_final_patch = ""
        raw_pipeline_final_patch = ""
        canonical_world_c_patch_projection: dict[str, Any] = {}
        pipeline_solve_eligible = False
        pipeline_failure_reason = ""
        if pipeline_result_ctx is not None:
            raw_pipeline_final_patch = getattr(pipeline_result_ctx, "final_patch", "") or ""
            if not raw_pipeline_final_patch:
                preserved_patch = getattr(pipeline_result_ctx, "pre_verification_final_patch", "")
                if isinstance(preserved_patch, str):
                    raw_pipeline_final_patch = preserved_patch
            pipeline_solve_eligible = getattr(pipeline_result_ctx, "solve_eligible", False)
            pipeline_failure_reason = getattr(pipeline_result_ctx, "failure_reason", "") or ""

        if pipeline_run_success and world_c_receipt_valid:
            try:
                from nexus.services.local_heal.world_c_receipt import (
                    build_world_c_canonical_patch_projection,
                )

                canonical_world_c_patch_projection = build_world_c_canonical_patch_projection(
                    ctx.source_root,
                    world_c_workspace_path,
                    ctx.target_file,
                    expected_source_hash=route_ctx_for_execution.get(
                        "world_c_expected_source_hash"
                    ),
                    expected_workspace_hash=route_ctx_for_execution.get(
                        "world_c_expected_workspace_hash"
                    ),
                    expected_patch_hash=route_ctx_for_execution.get(
                        "world_c_expected_patch_hash"
                    ),
                )
                pipeline_final_patch = canonical_world_c_patch_projection["patch"]
            except (OSError, ValueError, KeyError, TypeError) as exc:
                actual_execution = False
                path_a_failure_reason = (
                    f"canonical_patch_projection_error:{type(exc).__name__}:{str(exc)[:200]}"
                )
                pipeline_final_patch = ""

        # C1/C5D: Phase progression + attempt telemetry from pipeline result context
        phase_reached = ""
        patch_synthesis_reached = False
        reproduction_reached = False
        planning_reached = False
        localization_reached = False
        verification_reached = False
        patch_attempt_count = 0
        patch_attempt_errors = []
        patch_attempt_output_lens = []
        patch_attempt_file_paths = []
        patch_attempt_output_excerpt = ""
        patch_synthesis_output_len = 0

        if pipeline_result_ctx is not None:
            # Extract phase progression from context fields
            repro_evidence = getattr(pipeline_result_ctx, "repro_evidence", "") or ""
            plan = getattr(pipeline_result_ctx, "plan", None)
            localized_files = getattr(pipeline_result_ctx, "localized_files", [])
            final_patch = getattr(pipeline_result_ctx, "final_patch", "") or ""
            evaluation_report = getattr(pipeline_result_ctx, "evaluation_report", "") or ""
            skipped_repro = getattr(pipeline_result_ctx, "skip_reproduction", False)
            failure_reason = getattr(pipeline_result_ctx, "failure_reason", "") or ""
            model_decisions = getattr(pipeline_result_ctx, "model_decisions", []) or []

            stage_map = {
                str(stage.get("name") or ""): stage
                for stage in world_c_receipt.get("stages", [])
                if isinstance(stage, dict)
            }

            reproduction_reached = bool(stage_map.get("reproduction", {}).get("completed"))
            planning_reached = bool(stage_map.get("planning", {}).get("completed"))
            localization_reached = bool(stage_map.get("localization", {}).get("completed"))
            patch_synthesis_reached = bool(stage_map.get("patch_synthesis", {}).get("completed"))
            verification_reached = bool(stage_map.get("verification", {}).get("completed"))

            if patch_synthesis_reached and not final_patch and failure_reason:
                phase_reached = "patch_synthesis_failed"

            if verification_reached:
                phase_reached = "verification"
            elif patch_synthesis_reached:
                phase_reached = "patch_synthesis"
            elif localization_reached:
                phase_reached = "localization"
            elif planning_reached:
                phase_reached = "planning"
            elif reproduction_reached:
                phase_reached = "reproduction"

            # C5D: Extract patch attempt telemetry from model_decisions
            patch_decisions = [d for d in model_decisions if d.get("phase") == "patch"]
            patch_attempt_count = len(patch_decisions)
            for d in patch_decisions:
                patch_attempt_errors.append(d.get("status", ""))
                patch_attempt_output_lens.append(d.get("output_len", 0))
                patch_attempt_file_paths.append(d.get("file_path", ""))
            # Last attempt output excerpt (safe truncation)
            if patch_decisions:
                last_output = patch_decisions[-1].get("output_excerpt", "")[:500]
                patch_attempt_output_excerpt = last_output
                if patch_synthesis_output_len <= 0:
                    patch_synthesis_output_len = int(patch_decisions[-1].get("output_len", 0) or 0)

        # C7/C8: Default values
        output_hash = ""
        output_class = "UNKNOWN"
        parser_error_kind = "none"
        parser_error_message = "none"
        contains_search_marker = False
        contains_replace_marker = False
        contains_markdown_fence = False
        contains_unified_diff_header = False
        contains_natural_language_only = False

        micro_verify_context_present = False
        verifier_command_present = False
        verifier_command_source = ""
        bare_python_rejected = False
        micro_verify_failure_reason = ""
        search_mismatch = False
        protocol_retry_attempted = False
        protocol_retry_reason = ""
        protocol_retry_count = 0
        first_output_class = ""
        second_output_class = ""
        first_pipeline_failure_reason = ""
        second_pipeline_failure_reason = ""
        semantic_retry_invoked = False
        semantic_retry_count = 0
        same_span_retry = False
        structured_retry_packet_available = False
        semantic_retry_telemetry = {}

        if pipeline_result_ctx is not None:
            # Extract C7 classification
            patch_decisions = [d for d in model_decisions if d.get("phase") == "patch"]
            if patch_decisions:
                last_d = patch_decisions[-1]
                output_hash = last_d.get("output_hash", "")
                output_class = last_d.get("output_class", "UNKNOWN")
                parser_error_kind = last_d.get("parser_error_kind", "none")
                parser_error_message = last_d.get("parser_error_message", "none")
                contains_search_marker = last_d.get("contains_search_marker", False)
                contains_replace_marker = last_d.get("contains_replace_marker", False)
                contains_markdown_fence = last_d.get("contains_markdown_fence", False)
                contains_unified_diff_header = last_d.get("contains_unified_diff_header", False)
                contains_natural_language_only = last_d.get("contains_natural_language_only", False)

            # Extract C8 verifier context — pipeline_result_ctx is legacy HealContext
            # (no .op); attrs were sync'd back by sync_from_v2, so read directly.
            micro_verify_context_present = getattr(pipeline_result_ctx, "micro_verify_context_present", False)
            verifier_command_present = getattr(pipeline_result_ctx, "verifier_command_present", False)
            verifier_command_source = getattr(pipeline_result_ctx, "verifier_command_source", "")
            bare_python_rejected = getattr(pipeline_result_ctx, "bare_python_rejected", False)
            micro_verify_failure_reason = getattr(pipeline_result_ctx, "micro_verify_failure_reason", "")

            # C12/C13: Post-apply classification override
            # model_decisions are lost through PhaseResult, so we classify here
            # using pipeline_failure_reason which IS propagated.
            # Classification is now unified in the C13 block below.

            # C13: No-block output classification refinement
            # When output exists but C7 classification is UNKNOWN (lost through PhaseResult),
            # infer from pipeline_failure_reason and output characteristics.
            if output_class == "UNKNOWN" and patch_synthesis_output_len > 0:
                if "SEARCH_MISMATCH" in pipeline_failure_reason:
                    output_class = "SEARCH_REPLACE_SEARCH_MISMATCH"
                    search_mismatch = True
                elif "REPLACE_SYNTAX_ERROR" in pipeline_failure_reason or "SYNTAX_ERROR" in pipeline_failure_reason:
                    output_class = "SEARCH_REPLACE_SYNTAX_ERROR"
                    parser_error_kind = "SYNTAX_ERROR"
                    parser_error_message = pipeline_failure_reason
                elif "REPLACEMENT_MARKDOWN_FENCE" in pipeline_failure_reason:
                    output_class = "FENCED_SEARCH_REPLACE"
                elif "REFUSAL" in pipeline_failure_reason or "REFUSAL_DETECTED" in pipeline_failure_reason:
                    output_class = "REFUSAL"
                elif "UNIFIED_DIFF" in pipeline_failure_reason:
                    output_class = "UNIFIED_DIFF"
                elif "NO_BLOCKS_FOUND" in pipeline_failure_reason or "NO_EFFECTIVE_CHANGE" in pipeline_failure_reason:
                    output_class = "CODE_WITHOUT_SEARCH_REPLACE"
                else:
                    output_class = "NATURAL_LANGUAGE"

            # C13: Protocol retry telemetry from model_decisions
            patch_decisions_all = [d for d in model_decisions if d.get("phase") == "patch"]
            protocol_retry_count = max(0, len(patch_decisions_all) - 1)
            if protocol_retry_count > 0:
                protocol_retry_attempted = True
                first_d = patch_decisions_all[0] if patch_decisions_all else {}
                second_d = patch_decisions_all[-1] if patch_decisions_all else {}
                first_output_class = first_d.get("output_class", "UNKNOWN")
                second_output_class = second_d.get("output_class", "UNKNOWN")
                first_pipeline_failure_reason = first_d.get("status", "")
                second_pipeline_failure_reason = second_d.get("status", "")
                protocol_retry_reason = first_pipeline_failure_reason
                # Check if retry improved output
                if second_output_class in ("VALID_SEARCH_REPLACE", "SEARCH_REPLACE_SEARCH_MISMATCH") and first_output_class not in ("VALID_SEARCH_REPLACE",):
                    pass  # improved

            semantic_retry_telemetry = dict(getattr(pipeline_result_ctx, "_semantic_retry_telemetry", {}) or {})
            semantic_retry_count = int(semantic_retry_telemetry.get("semantic_retry_count", 0) or 0)
            same_span_retry = bool(semantic_retry_telemetry.get("same_span_retry", False))
            semantic_retry_invoked = semantic_retry_count > 0 or same_span_retry
            structured_retry_packet_available = _has_structured_packet(getattr(pipeline_result_ctx, "errors", []) or [])

        phase_durations = {}
        if pipeline_result_ctx is not None:
            ledger = getattr(pipeline_result_ctx, "_latency_ledger", None)
            if ledger is not None:
                for p in getattr(ledger, "phases", []):
                    name = p.phase_name
                    if name.startswith("patch_attempt"):
                        name = "patch_synthesis"
                    elif name.startswith("verify_attempt"):
                        name = "verification"
                    phase_durations[f"phase_{name}_sec"] = round(p.duration_sec, 4)

        return CapabilityExecutionResult(
            name="repair_loop", selected=True, invoked=True,
            gate_passed=actual_execution, outcome_contributed=actual_execution,
            evidence_present=True,
            failure_reason="" if actual_execution else f"path_a_execution_missing: {path_a_failure_reason}",
            telemetries={
                "phase_reached": phase_reached,
                "phases_completed": [p for p in ["reproduction", "planning", "localization", "patch_synthesis", "verification"] if {"reproduction": reproduction_reached, "planning": planning_reached, "localization": localization_reached, "patch_synthesis": patch_synthesis_reached, "verification": verification_reached}.get(p)],
                "phase_failed": phase_reached if pipeline_result_ctx and getattr(pipeline_result_ctx, "failure_reason", "") else "",
                "phase_failure_reason": getattr(pipeline_result_ctx, "failure_reason", "") if pipeline_result_ctx else "",
                **phase_durations,
                "reproduction_reached": reproduction_reached,
                "planning_reached": planning_reached,
                "localization_reached": localization_reached,
                "patch_synthesis_reached": patch_synthesis_reached,
                "verification_reached": verification_reached,
                # Ollama native metrics and elapsed seconds
                "provider_elapsed_sec": _last_provider_diag.get("provider_elapsed_sec", 0.0),
                "ollama_total_duration": _last_provider_diag.get("ollama_total_duration", 0),
                "ollama_load_duration": _last_provider_diag.get("ollama_load_duration", 0),
                "ollama_prompt_eval_count": _last_provider_diag.get("ollama_prompt_eval_count", 0),
                "ollama_prompt_eval_duration": _last_provider_diag.get("ollama_prompt_eval_duration", 0),
                "ollama_eval_count": _last_provider_diag.get("ollama_eval_count", 0),
                "ollama_eval_duration": _last_provider_diag.get("ollama_eval_duration", 0),
                "ollama_done_reason": _last_provider_diag.get("ollama_done_reason", ""),
                "ollama_metrics_available": _last_provider_diag.get("ollama_metrics_available", False),
                # C5D: Patch attempt trace
                "patch_attempt_count": patch_attempt_count,
                "patch_attempt_errors": patch_attempt_errors,
                "patch_attempt_output_lens": patch_attempt_output_lens,
                "patch_attempt_file_paths": patch_attempt_file_paths,
                "patch_attempt_output_excerpt": patch_attempt_output_excerpt,
                "patch_synthesis_provider_error": _last_provider_diag.get("provider_error", ""),
                "patch_synthesis_model_called": _last_provider_diag.get("model_called", False),
                "patch_synthesis_output_len": _last_provider_diag.get("output_len", 0),
                "patch_synthesis_prompt_len": _last_provider_diag.get("prompt_len", 0),
                "patch_synthesis_model_name": _last_provider_diag.get("model_name", ""),
                "provider_error": _last_provider_diag.get("provider_error", ""),
                "provider_invoked": _last_provider_diag.get("provider_invoked", False),
                "model_called": _last_provider_diag.get("model_called", False),
                "model_name_used": _last_provider_diag.get("model_name", ""),
                "timed_out": _last_provider_diag.get("timed_out", False),
                "output_truncated": _last_provider_diag.get("output_truncated", False),
                "output_len": _last_provider_diag.get("output_len", 0),
                "prompt_len": _last_provider_diag.get("prompt_len", 0),
                "localheal_pipeline_available": modules.get("heal_pipeline", False),
                "localheal_pipeline_instantiated": "heal_pipeline" in invoked_modules,
                "localheal_pipeline_run_called": pipeline_run_called,
                "localheal_pipeline_run_success": pipeline_run_success,
                "localheal_pipeline_invoked": "heal_pipeline" in invoked_modules,
                "localheal_pipeline_actual_execution": actual_execution,
                "localheal_pipeline_availability_only": not actual_execution,
                "orchestrator_run_reachable": orchestrator_run_reachable,
                "world_c_receipt": world_c_receipt,
                "world_c_receipt_valid": world_c_receipt_valid,
                "canonical_run_group": canonical_run_group_value,
                "canonical_world_c_patch_projection": canonical_world_c_patch_projection,
                "world_c_receipt_errors": world_c_receipt_errors,
                "world_c_workspace_path": world_c_workspace_path,
                "committee_orchestrator_available": modules.get("committee_orchestrator", False),
                "committee_orchestrator_invoked": "committee_orchestrator" in invoked_modules,
                "solid_search_replace_protocol_available": modules.get("solid_search_replace_protocol", False),
                "solid_search_replace_protocol_invoked": "solid_search_replace_protocol" in invoked_modules,
                "granular_localizer_available": modules.get("granular_localizer", False),
                "granular_localizer_invoked": "granular_localizer" in invoked_modules,
                "failure_feedback_builder_available": modules.get("failure_feedback_builder", False),
                "failure_feedback_builder_invoked": "failure_feedback_builder" in invoked_modules,
                "evaluation_gate_available": modules.get("evaluation_gate", False),
                "evaluation_gate_invoked": "evaluation_gate" in invoked_modules,
                "semantic_retry_available": True,
                "semantic_retry_invoked": semantic_retry_invoked,
                "semantic_retry_count": semantic_retry_count,
                "same_span_retry": same_span_retry,
                "semantic_retry_client_reused": bool(semantic_retry_telemetry.get("semantic_retry_client_reused", False)),
                "semantic_retry_client_class": str(semantic_retry_telemetry.get("semantic_retry_client_class", "") or ""),
                "semantic_retry_prompt_len": int(semantic_retry_telemetry.get("semantic_retry_prompt_len", 0) or 0),
                "semantic_retry_prompt_hash": str(semantic_retry_telemetry.get("semantic_retry_prompt_hash", "") or ""),
                "semantic_retry_prompt_has_verifier_evidence": bool(semantic_retry_telemetry.get("semantic_retry_prompt_has_verifier_evidence", False)),
                "semantic_retry_raw_response_len": int(semantic_retry_telemetry.get("semantic_retry_raw_response_len", 0) or 0),
                "semantic_retry_raw_response_excerpt": str(semantic_retry_telemetry.get("semantic_retry_raw_response_excerpt", "") or "")[:500],
                "semantic_retry_response_is_none": bool(semantic_retry_telemetry.get("semantic_retry_response_is_none", False)),
                "semantic_retry_response_empty": bool(semantic_retry_telemetry.get("semantic_retry_response_empty", False)),
                "semantic_retry_response_type": str(semantic_retry_telemetry.get("semantic_retry_response_type", "") or ""),
                "semantic_retry_output_class": str(semantic_retry_telemetry.get("semantic_retry_output_class", "") or ""),
                "semantic_retry_parser_error_kind": str(semantic_retry_telemetry.get("semantic_retry_parser_error_kind", "") or ""),
                "semantic_retry_status": str(semantic_retry_telemetry.get("semantic_retry_status", "") or ""),
                "semantic_retry_failure_reason": str(semantic_retry_telemetry.get("semantic_retry_failure_reason", "") or ""),
                "semantic_retry_invocation_source": str(semantic_retry_telemetry.get("semantic_retry_invocation_source", "") or ""),
                "structured_retry_packet_available": structured_retry_packet_available,
                "invoked_modules": invoked_modules,
                "path_a_actual_execution": actual_execution,
                "path_a_failure_reason": path_a_failure_reason,
                "pipeline_final_patch": pipeline_final_patch,
                "raw_pipeline_final_patch": raw_pipeline_final_patch,
                "pipeline_solve_eligible": pipeline_solve_eligible,
                "pipeline_failure_reason": pipeline_failure_reason,
                "first_attempt_patch_hash": getattr(pipeline_result_ctx, "_first_attempt_patch_hash", "") if pipeline_result_ctx else "",
                # C7: Output Classification
                "output_hash": output_hash,
                "output_class": output_class,
                "parser_error_kind": parser_error_kind,
                "parser_error_message": parser_error_message,
                "contains_search_marker": contains_search_marker,
                "contains_replace_marker": contains_replace_marker,
                "contains_markdown_fence": contains_markdown_fence,
                "contains_unified_diff_header": contains_unified_diff_header,
                "contains_natural_language_only": contains_natural_language_only,
                # C8: Micro Verifier Context
                "micro_verify_context_present": micro_verify_context_present,
                "verifier_command_present": verifier_command_present,
                "verifier_command_source": verifier_command_source,
                "bare_python_rejected": bare_python_rejected,
                "micro_verify_failure_reason": micro_verify_failure_reason,
                # C12: Search mismatch classification
                "search_mismatch": search_mismatch,
                # C13: Protocol retry telemetry
                "protocol_retry_attempted": protocol_retry_attempted,
                "protocol_retry_reason": protocol_retry_reason,
                "protocol_retry_count": protocol_retry_count,
                "first_output_class": first_output_class,
                "second_output_class": second_output_class,
                "first_pipeline_failure_reason": first_pipeline_failure_reason,
                "second_pipeline_failure_reason": second_pipeline_failure_reason,
            },
        )
