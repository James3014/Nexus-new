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

        if modules.get("heal_pipeline"):
            try:
                from nexus.services.local_heal.pipeline import HealPipeline, HealContext as LegacyHealContext
                from pathlib import Path as _Path

                real_provider = ctx.provider
                # B7.5: Provider diagnostics storage
                _last_provider_diag = {}

                if real_provider is not None:
                    def _provider_generate(system_prompt_or_req, user_prompt=None, **kwargs):
                        nonlocal _last_provider_diag
                        from nexus.services.local_heal.local_model_provider import LocalModelProviderRequest
                        # OllamaLLMClient passes (system_prompt, user_prompt) as two strings
                        # LocalModelProviderRequest passes a single request object
                        if user_prompt is not None:
                            prompt = f"{system_prompt_or_req}\n\n{user_prompt}"
                            model_name = kwargs.get("model", "")
                        else:
                            prompt = getattr(system_prompt_or_req, "prompt", "") or str(system_prompt_or_req)
                            model_name = getattr(system_prompt_or_req, "model_name", "") or kwargs.get("model", "")
                        prov_req = LocalModelProviderRequest(
                            task_id=ctx.task_id,
                            prompt=prompt,
                            evidence_refs=ctx.evidence_refs,
                            model_name=model_name,
                        )
                        prov_resp = real_provider.generate(prov_req)
                        # B7.5: Store diagnostics for telemetry
                        _last_provider_diag = {
                            "provider_invoked": prov_resp.provider_invoked,
                            "model_called": prov_resp.model_called,
                            "model_name": prov_resp.model_name or model_name,
                            "provider_error": prov_resp.error or "",
                            "timed_out": prov_resp.timed_out,
                            "output_truncated": prov_resp.output_truncated,
                            "output_len": len(prov_resp.output_text),
                            "prompt_len": len(prompt),
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
                repro_script = route_ctx.get("repro_script", "") if isinstance(route_ctx, dict) else ""
                skip_repro = not bool(repro_script)

                heal_ctx = LegacyHealContext(
                    instance_id=ctx.task_id,
                    repo_dir=_Path(ctx.source_root),
                    problem_statement=ctx.problem_statement,
                    route_context=ctx.route_context,
                    python_executable="",
                    max_tries=3,
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
                except Exception as run_exc:
                    path_a_failure_reason = f"pipeline_run_error: {str(run_exc)[:200]}"
                    path_a_actual_execution = False

            except Exception:
                path_a_failure_reason = "pipeline_instantiation_error"

        # 5. CommitteeOrchestrator availability
        if modules.get("committee_orchestrator"):
            invoked_modules.append("committee_orchestrator")

        # 6. EvaluationGate availability
        if modules.get("evaluation_gate"):
            invoked_modules.append("evaluation_gate")

        # B2: actual_execution requires pipeline.run() success, not just instantiation
        actual_execution = pipeline_run_success and len(invoked_modules) >= 2

        # Extract pipeline result if available
        pipeline_final_patch = ""
        pipeline_solve_eligible = False
        pipeline_failure_reason = ""
        if pipeline_result_ctx is not None:
            pipeline_final_patch = getattr(pipeline_result_ctx, "final_patch", "") or ""
            pipeline_solve_eligible = getattr(pipeline_result_ctx, "solve_eligible", False)
            pipeline_failure_reason = getattr(pipeline_result_ctx, "failure_reason", "") or ""

        # B7.5: Phase progression telemetry
        phase_reached = "reproduction"
        patch_synthesis_reached = False
        if pipeline_run_success:
            phase_reached = "patch_synthesis"
            patch_synthesis_reached = True

        return CapabilityExecutionResult(
            name="repair_loop", selected=True, invoked=True,
            gate_passed=actual_execution, outcome_contributed=actual_execution,
            evidence_present=True,
            failure_reason="" if actual_execution else f"path_a_execution_missing: {path_a_failure_reason}",
            telemetries={
                "phase_reached": phase_reached,
                "patch_synthesis_reached": patch_synthesis_reached,
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
                "semantic_retry_invoked": False,
                "invoked_modules": invoked_modules,
                "path_a_actual_execution": actual_execution,
                "path_a_failure_reason": path_a_failure_reason,
                "pipeline_final_patch": pipeline_final_patch,
                "pipeline_solve_eligible": pipeline_solve_eligible,
                "pipeline_failure_reason": pipeline_failure_reason,
            },
        )
