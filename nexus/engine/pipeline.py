from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import logging
import time
import json
import subprocess
import sys
import dataclasses
from dataclasses import dataclass, field
import os
from datetime import datetime, timezone

# 基礎與工具導入
from nexus.delivery.phantom_guard import detect_inconclusive_success
from nexus.core.state_contracts import NexusState
from nexus.core.skill_outcomes import build_outcome_event, append_skill_outcome_event
from nexus.research.research_pack import build_research_pack
from nexus.learning.skill_artifact import build_skill_artifact
from nexus.learning.knowledge_index import KnowledgeIndex
from nexus.learning.skill_registry import SkillRegistry
from nexus.learning.skill_exchange import SkillExchange
from nexus.learning.skill_store import SkillStore
from nexus.events.transport import NexusEventBus
from nexus.events.store import EventStore
from nexus.events.contracts import NexusEvent, build_lifecycle_hook_event, build_phase_transition_event
from nexus.telemetry.otel_config import init_otel
from nexus.telemetry.tracer import NexusTracer
from nexus.engine.cli_pregate import run_cli_pregate, _auto_detect_verify_commands
from nexus.learning.cycle_analyzer import analyze_cycle
from nexus.engine.pipeline_outcome import PipelineOutcome, PipelineTerminalState, HumanReviewHandoff
from nexus.core.outcome_schema import NexusOutcomeV2
from nexus.core.handoff_bundle import HandoffBundleWriter
from nexus.engine.phase_plugin import PhaseRegistry, PhasePlugin, PhaseResult, PhaseExecutor

# Mixins 導入
from nexus.engine.pipeline_stages import PipelineStagesMixin
from nexus.engine.pipeline_repair import PipelineRepairMixin
from nexus.engine.pipeline_crystal import PipelineCrystalMixin
from nexus.engine.pipeline_research import PipelineResearchMixin

logger = logging.getLogger(__name__)
CANONICAL_STAGE_FLOW = ["S", "P", "X", "D", "R", "A", "C"]
STAGE_DESCRIPTIONS = {
    "S": "cold_start_seed",
    "P": "plan",
    "X": "research_xray",
    "D": "diagnose",
    "R": "repair",
    "A": "audit_acceptance",
    "C": "crystallize",
}

@dataclass
class PipelineContext:
    """一次 Pipeline 執行的所有共享狀態 (v23.8 Hardened - Bayesian Core)"""
    state: NexusState
    task_desc: str
    task_type: str
    task_id: str
    kwargs: dict
    dry_run: bool
    # Engine component shortcuts
    hub: Any
    accumulator: Any
    health_evaluator: Any
    research_policy: Any
    # Registry and Tracer
    registry: PhaseRegistry = field(default_factory=PhaseRegistry)
    tracer: Any = None
    
    # Bayesian Evolution Hook
    bayesian_params: Dict[str, Any] = field(default_factory=dict)
    
    # Mutable inter-stage data
    decision_counter: int = 0
    prediction: Any = None
    research_pack: Any = None
    planner: Any = None
    researcher: Any = None
    repairer: Any = None
    pack: dict = field(default_factory=dict)
    event_store: Any = None  # Atomic Sinking (R16)
    outcome_v2: Optional[NexusOutcomeV2] = None
    decision_journal: list[dict[str, Any]] = field(default_factory=list)

    def append_journal(self, *, origin_phase: str, event_type: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Append-only blackboard event with provenance."""
        event = {
            "origin_phase": origin_phase,
            "event_type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": dict(payload or {}),
        }
        self.decision_journal.append(event)
        return event

class NexusPipeline(
    PipelineStagesMixin, 
    PipelineRepairMixin, 
    PipelineCrystalMixin, 
    PipelineResearchMixin
):
    """⚙️ Nexus Task Pipeline (P-X-D-R-A-C v24.0 Enhanced)
    
    IDENTITY: Nexus is a Battlesuit (戰甲).
    [EVOLUTION LOG]:
    - Round 1-5: Decoupling phase mapping.
    - Round 6-12: Atomic event sinking integration.
    - Round 13-20: Bayesian health scoring & Dynamic lifecycle hooks.
    """
    
    PHASE_PRIORITY_MAP = {"P": 10, "X": 20, "D": 25, "R": 30, "A": 40, "C": 50}

    def __init__(self, engine):
        self.engine = engine
        self.registry = PhaseRegistry()
        self._register_default_plugins()

    def _init_stage_status(self, state: NexusState) -> None:
        state.metadata.setdefault("stage_flow", list(CANONICAL_STAGE_FLOW))
        state.metadata.setdefault("stage_descriptions", dict(STAGE_DESCRIPTIONS))
        state.metadata.setdefault("stage_status", {stage: "pending" for stage in CANONICAL_STAGE_FLOW})

    def _mark_stage(self, state: NexusState, stage: str, status: str) -> None:
        self._init_stage_status(state)
        state.metadata["stage_status"][stage] = status

    def _register_default_plugins(self):
        """Registers standard phases using the core PHASES_MAP (MUSE-PLUGIN-2.0)."""
        phase_executors = getattr(self.engine, "phase_executors", None)
        if phase_executors:
            self._register_phase_executors(phase_executors)
            return

        if not hasattr(self.engine, 'phases') or not self.engine.phases:
            return
            
        from nexus.engine.phase_plugin import PhasePlugin, PhaseResult

        class _LegacyPhaseAdapter(PhasePlugin):
            METHOD_MAP = {
                "P": "_stage_plan",
                "X": "_stage_research",
                "C": "_stage_crystallize",
            }

            def __init__(self, name, handler, pipeline):
                super().__init__(name, priority=NexusPipeline.PHASE_PRIORITY_MAP.get(name, 100))
                self.handler = handler
                self.pipeline = pipeline

            def should_run(self, ctx: PipelineContext):
                # 🧪 Bayesian Thresholding: Dynamic X-Ray decision
                if self.name == "X":
                    nas_aggression = ctx.bayesian_params.get("nas_aggression", 0.5)
                    force = bool(ctx.state.metadata.get("benchmark_force_research"))
                    should = bool(ctx.state.metadata.get("research_route", {}).get("should_research"))
                    return force or should or (nas_aggression > 0.8)
                return True

            def execute(self, pipeline, ctx: PipelineContext) -> PhaseResult:
                # 🛡️ Dynamic Method Dispatching with Atomic Sinking
                method_name = self.METHOD_MAP.get(self.name)
                if not method_name or not hasattr(pipeline, method_name):
                    return PhaseResult(status="skip", mutations={}, events=[])
                
                try:
                    # 🚀 [v24.0] Pre-Phase Lifecycle Hook
                    ctx.event_store.append(
                        build_lifecycle_hook_event(
                            task_id=ctx.task_id,
                            phase=self.name,
                            hook="pre",
                            payload={"nas_aggression": ctx.bayesian_params.get("nas_aggression", 0.0)},
                        )
                    )

                    # 🧪 [Round 20] Non-blocking Execution Guard
                    start_ts = time.time()
                    method = getattr(pipeline, method_name)
                    if self.name == "C":
                        success = ctx.state.metadata.get("pipeline_success", False)
                        method(ctx, success, ctx.tracer)
                    else:
                        method(ctx, ctx.tracer)
                    
                    elapsed = time.time() - start_ts
                    logger.info(f"⚡ [Pipe:v24.0] Phase {self.name} finished in {elapsed:.2f}s (No deadlock).")
                        
                    return PhaseResult(status="success", mutations={}, events=[])
                except Exception as e:
                    logger.error(f"❌ Phase {self.name} failed: {e}", exc_info=True)
                    return PhaseResult(status="fail", mutations={}, events=[])

        self._register_phase_executors(self._build_default_phase_executors())
        if self.registry.get_ordered_plugins():
            return

        # Keep only phases that still have an accepted legacy fallback. Diagnose is
        # intentionally composition-only so executor bootstrap failures do not
        # silently re-enable the old mixin path.
        core_phases = ["P", "X"]
        composition_only_phases = {"D"}
        for name in core_phases:
            p_handler = self.engine.phases.get(name)
            if p_handler:
                self.registry.register(_LegacyPhaseAdapter(name, p_handler, self))

        # 註冊其餘階段（包括 C 結晶階段）
        for name, p_handler in self.engine.phases.items():
            if name in core_phases or name in composition_only_phases or not p_handler:
                continue
            
            if isinstance(p_handler, PhasePlugin):
                self.registry.register(p_handler)
            else:
                self.registry.register(_LegacyPhaseAdapter(name, p_handler, self))

    def _build_default_phase_executors(self) -> Dict[str, PhaseExecutor]:
        project_root = getattr(self.engine, "project_root", None)
        run_dir = getattr(self.engine, "run_dir", None)
        if project_root is None or run_dir is None:
            return {}
        try:
            from nexus.engine.phase_executors import (
                build_audit_executor,
                build_crystallize_executor,
                build_diagnose_executor,
                build_plan_executor,
                build_repair_executor,
                build_research_executor,
            )

            return {
                "P": build_plan_executor(project_root, run_dir),
                "X": build_research_executor(project_root, run_dir),
                "D": build_diagnose_executor(project_root, run_dir, hub=getattr(self.engine, "hub", None)),
                "R": build_repair_executor(project_root, run_dir),
                "A": build_audit_executor(project_root, run_dir),
                "C": build_crystallize_executor(project_root, run_dir),
            }
        except Exception as exc:
            logger.debug("phase_executor_bootstrap_skipped: %s", exc)
            return {}

    def _register_phase_executors(self, phase_executors: Dict[str, PhaseExecutor]) -> None:
        for name in ("P", "X", "D", "R", "A", "C"):
            executor = phase_executors.get(name)
            if executor is not None:
                self.registry.register(_PhaseExecutorPlugin(name, executor))

    def _run_crystallize_phase(self, ctx: PipelineContext, success: bool, tracer: Any) -> None:
        ctx.state.metadata["pipeline_success"] = success
        plugin = next((item for item in self.registry.get_ordered_plugins() if item.name == "C"), None)
        if plugin is not None and plugin.should_run(ctx):
            result = plugin.execute(self, ctx)
            mutations = dict(getattr(result, "mutations", None) or {})
            ctx.state.metadata["composition_crystallize_phase_status"] = str(getattr(result, "status", ""))
            ctx.state.metadata["composition_crystallize_phase_mutations"] = mutations
            if self._crystallize_side_effects_present(ctx):
                ctx.state.metadata["composition_crystallize_side_effects_verified"] = True
                return
            ctx.state.metadata["composition_crystallize_side_effects_verified"] = False
            ctx.state.metadata["composition_crystallize_fallback_reason"] = "missing_terminal_outcome_side_effects"
            self._stage_crystallize(ctx, success, tracer)
            return
        self._stage_crystallize(ctx, success, tracer)

    @staticmethod
    def _crystallize_side_effects_present(ctx: PipelineContext) -> bool:
        metadata = ctx.state.metadata
        return bool(
            metadata.get("pipeline_terminal_state")
            and metadata.get("pipeline_outcome")
            and metadata.get("nexus_outcome_v2")
        )

    def run(self, task_desc: str, task_type: str = "bug", context: Optional[Dict] = None, **kwargs) -> bool:
        """EntryPoint for P-X-D-R-A-C pipeline with OTel Tracing wrapper."""
        try:
            init_otel(project_root=self.engine.project_root)
        except Exception:
            logger.debug("otel_init_skipped")

        tracer = NexusTracer()
        task_id = kwargs.pop("task_id", f"{task_type}-{int(time.time())}")
        
        # Identity Enforcement Log
        logger.info(f"🛡️ Nexus Battlesuit activated for task: {task_id}")

        with tracer.pipeline_span(task_id, **{"nexus.mode": kwargs.get("mode", "developer")}) as (root_span, trace_id, span_id):
            return self._run_pipeline_inner(task_id, trace_id, span_id, task_desc, task_type, context, tracer, **kwargs)

    def _init_pipeline_state(self, task_id: str, trace_id: str, span_id: str, task_desc: str, task_type: str, context: Optional[Dict], **kwargs) -> PipelineContext:
        NexusEventBus.configure(self.engine.project_root)
        state = NexusState(task_id=task_id)
        state.trace_id = trace_id
        state.span_id = span_id
        state.metadata["task_description"] = task_desc
        state.metadata.setdefault("phase_decisions", {})
        state.metadata.setdefault("phase_skills", {})
        state.metadata.setdefault("escalation_count", 0)
        dry_run_mode = bool(kwargs.get("dry_run"))
        state.metadata["effort_level"] = str(kwargs.get("effort", context.get("effort_level", "unknown") if context else "unknown"))
        if context:
            state.metadata.update(context)
            
        # [NEW: P-1] Claims Pre-flight Guard
        try:
            from nexus.research.learn_mode import LearnModeService
            svc = LearnModeService(self.engine.project_root)
            trap_check = svc.ask(topic="known-pitfalls", question=task_desc, top_k=3)
            if trap_check.get("citations"):
                state.metadata["claims_pre_flight"] = [
                    f"⚠️ {c['claim']}" for c in trap_check["citations"][:3]
                ]
                logger.info(f"🛡️ [Pre-flight] Loaded {len(trap_check['citations'])} known pitfalls from Claims.")
        except Exception as e:
            logger.debug(f"Pre-flight claims check skipped: {e}")

            
        self.engine.policy_manager.apply_policy_to_state(state, task_desc)
        # Ensure description persists after policy logic
        state.metadata["task_description"] = task_desc
        
        self.engine.state_io.save_global_state(state)
        self.engine.commander.next_step(status="started")
        
        ctx = PipelineContext(
            state=state,
            task_desc=task_desc,
            task_type=task_type,
            task_id=task_id,
            kwargs=kwargs,
            dry_run=dry_run_mode,
            hub=self.engine.hub,
            accumulator=self.engine.accumulator,
            health_evaluator=self.engine.health_evaluator,
            research_policy=self.engine.research_policy,
            event_store=EventStore(),
            planner=self.engine.phases.get("P"),
            researcher=self.engine.phases.get("X"),
            repairer=self.engine.phases.get("R"),
            pack={"task": task_desc}, # 🛡️ Ensure BasePhaseHandler.execute sees the task
            outcome_v2=NexusOutcomeV2(task_id=task_id)
        )
        return ctx

    def _finalize_and_report(self, ctx: PipelineContext, success: bool, tracer: Any) -> bool:
        if ctx.event_store:
            try:
                event_log_path = self.engine.run_dir / "events_sourced.jsonl"
                ctx.event_store.save_to_file(str(event_log_path))
                logger.info("📜 State events sourced to: %s", event_log_path.name)
            except Exception as e:
                logger.debug("event_source_save_failed: %s", e)

        health_score = ctx.health_evaluator.evaluate(ctx.state, success)
        logger.info(f"📊 Final Health: {health_score:.1f}% | Success: {success}")

        # Update Outcome V2 telemetry
        if ctx.outcome_v2:
            ctx.outcome_v2.success = success
            ctx.outcome_v2.health_score = health_score
            ctx.outcome_v2.terminal_state = ctx.state.metadata.get("pipeline_terminal_state", "UNKNOWN")

        self.engine.state_io.save_global_state(ctx.state)
        
        terminal_state = ctx.state.metadata.get("pipeline_terminal_state", "UNKNOWN")
        
        if not success or terminal_state in ("FAILED", "HUMAN_REVIEW", "ESCALATED"):
            try:
                from nexus.delivery.incident_pack import collect_incident_pack
                collect_incident_pack(self.engine.run_dir, ctx.task_id, ctx.task_desc, terminal_state, self.engine.project_root)
            except Exception as e:
                logger.error(f"Failed to collect incident pack: {e}")

        if terminal_state == "HUMAN_REVIEW":
            logger.error("🛑 Pipeline 終止於 HUMAN_REVIEW，需人工介入")
            try:
                writer = HandoffBundleWriter(self.engine.project_root)
                writer.create(
                    triggering_phase="pipeline_terminal",
                    reason=ctx.state.metadata.get("human_review_reason", "HUMAN_REVIEW triggered"),
                    task_id=ctx.task_id,
                    trace_id=ctx.state.metadata.get("trace_id", ""),
                    decision_id=str(ctx.state.metadata.get("last_decision_id", "")),
                    agent_history=[h.phase for h in ctx.state.steps_history],
                    state_variables={
                        "escalation_count": ctx.state.metadata.get("escalation_count", 0),
                        "sandbox_mode": ctx.state.metadata.get("sandbox_mode", "unknown"),
                        "final_health": health_score
                    },
                )
            except Exception as e:
                logger.error(f"Handoff bundle creation failed: {e}")
        elif terminal_state == "ESCALATED":
            logger.warning("📢 Pipeline 終止於 ESCALATED，Coordinator 應重新規劃")
            
        # === NEW: Final Safety Valve ===
        # 即使所有 Phase 都報告 success，也要檢查是否有被繞過的 gate
        pregate_unverified = bool(ctx.state.metadata.get("pregate_unverified"))
        evidence_low_trust = bool(ctx.state.metadata.get("evidence_trust_rejection"))
        plan_rejected = bool(ctx.state.metadata.get("plan_reject_reason"))
        
        if success and (pregate_unverified or evidence_low_trust or plan_rejected):
            logger.warning("🛡️ [Safety Valve] Success overridden by unresolved governance signals.")
            ctx.state.metadata["safety_valve_triggered"] = True
            ctx.state.metadata["safety_valve_reasons"] = {
                "pregate_unverified": pregate_unverified,
                "evidence_low_trust": evidence_low_trust,
                "plan_rejected": plan_rejected,
            }
            # 不直接改 success，但在 outcome 中標記需要人工確認
            if ctx.outcome_v2:
                ctx.outcome_v2.trust_level = "degraded"
                ctx.outcome_v2.terminal_state = "HUMAN_REVIEW"
            ctx.state.metadata["pipeline_terminal_state"] = "HUMAN_REVIEW"
            ctx.state.metadata["human_review_reason"] = "safety_valve_triggered"
            
            # === NEW: Iron Gate Phase 2 布林值翻轉 ===
            success = False
            
        return success

    def _run_pipeline_inner(self, task_id: str, trace_id: str, span_id: str, task_desc: str, task_type: str = "bug", context: Optional[Dict] = None, tracer: Any = None, **kwargs) -> bool:
        """執行核心 P-X-D-R-A-C 管線 (Sprint 13 R15 Plugin-driven)"""
        ctx = self._init_pipeline_state(task_id, trace_id, span_id, task_desc, task_type, context, **kwargs)
        ctx.tracer = tracer
        
        success = True
        spec_binding = self._stage_spec_bind(ctx)
        logger.info(
            "🧭 [S-Stage] Spec binding enabled=%s reason=%s targets=%d verify_cmds=%d",
            spec_binding.get("enabled"),
            spec_binding.get("reason"),
            spec_binding.get("target_files_count", 0),
            spec_binding.get("verify_commands_count", 0),
        )
        
        # 1. 執行線性階段 (P -> X -> D)
        pxd_attempts = 0
        MAX_PXD_RETRIES = 2
        
        while pxd_attempts < MAX_PXD_RETRIES and success:
            pxd_attempts += 1
            pxd_veto = False
            
            is_direct_mode = bool(ctx.state.metadata.get("direct_mode", False))
            if is_direct_mode:
                logger.info("⚡ [Pipeline] Direct Mode active: Bypassing P-X-D formulation phases.")
                break
                
            for plugin in self.registry.get_ordered_plugins():
                if plugin.name in ("P", "X", "D"):
                    if not plugin.should_run(ctx):
                        logger.info("⏩ Skipping phase: %s", plugin.name)
                        continue
                        
                    logger.info("🚀 [Pipeline] Executing Plugin Phase: %s", plugin.name)
                    
                    ctx.event_store.append(
                        build_phase_transition_event(
                            task_id=ctx.task_id,
                            phase=plugin.name,
                            transition="start",
                            payload={"name": plugin.name},
                        )
                    )
                    
                    try:
                        result = plugin.execute(self, ctx)
                        
                        ctx.event_store.append(
                            build_phase_transition_event(
                                task_id=ctx.task_id,
                                phase=plugin.name,
                                transition="end",
                                payload={"status": result.status},
                            )
                        )
                        
                        if result.status in {"FAILED", "fail"}:
                            logger.error("❌ Phase %s failed, terminating pipeline.", plugin.name)
                            success = False
                            ctx.state.metadata["pipeline_terminal_state"] = "FAILED"
                            break
                    except RuntimeError as veto_err:
                        veto_str = str(veto_err)
                        if "VETO" in veto_str and pxd_attempts < MAX_PXD_RETRIES:
                            logger.warning("🔄 [Pipeline] D-Stage VETO → Feeding back to P-Stage for replan (Attempt %d/%d)", pxd_attempts, MAX_PXD_RETRIES)
                            ctx.kwargs["veto_feedback"] = veto_str
                            pxd_veto = True
                            break  # Break inner for loop, retry outer while loop
                        elif "VETO" in veto_str or "Plan Quality Gate" in veto_str:
                            logger.error("🛑 [Pipeline] Governance VETO terminal: %s", veto_err)
                            success = False
                            ctx.state.metadata["pipeline_terminal_state"] = "FAILED"
                            ctx.state.metadata["governance_veto_reason"] = veto_str
                            break
                        raise  # 非治理異常，繼續上拋
                    except Exception as e:
                        logger.exception(f"Unhandled failure in plugin {plugin.name}: {e}")
                        success = False
                        ctx.state.metadata["pipeline_terminal_state"] = "FAILED"
                        break
            
            if not pxd_veto:
                break  # P-X-D 全部通過或 terminal failure，跳出
            
        # 2. 執行複雜循環階段 (R/A)
        if success:
            try:
                success = self._repair_audit_loop(ctx, tracer)
            except Exception as e:
                logger.exception(f"Fatal error in Repair-Audit loop: {e}")
                success = False
                ctx.state.metadata["pipeline_terminal_state"] = "FAILED"
        
        # 3. 執行結晶與結案
        # --- C Stage: Crystallize ---
        try:
            self._run_crystallize_phase(ctx, success, tracer)
        except Exception as e:
            logger.error(f"Crystallize stage encountered an error (non-fatal): {e}")
            
        return self._finalize_and_report(ctx, success, tracer)


class _PhaseExecutorPlugin(PhasePlugin):
    """Plugin shell that delegates phase behavior to composition executors."""

    def __init__(self, name: str, executor: PhaseExecutor):
        super().__init__(name, priority=NexusPipeline.PHASE_PRIORITY_MAP.get(name, getattr(executor, "priority", 100)))
        self.executor = executor

    def should_run(self, ctx: PipelineContext) -> bool:
        if self.name == "X":
            nas_aggression = ctx.bayesian_params.get("nas_aggression", 0.5)
            force = bool(ctx.state.metadata.get("benchmark_force_research"))
            should = bool(ctx.state.metadata.get("research_route", {}).get("should_research"))
            if not (force or should or (nas_aggression > 0.8)):
                return False
        should_run = getattr(self.executor, "should_run", None)
        return bool(should_run(ctx)) if callable(should_run) else True

    def execute(self, pipeline: NexusPipeline, ctx: PipelineContext) -> PhaseResult:
        ctx.event_store.append(
            build_lifecycle_hook_event(
                task_id=ctx.task_id,
                phase=self.name,
                hook="pre",
                payload={"nas_aggression": ctx.bayesian_params.get("nas_aggression", 0.0)},
            )
        )
        return self.executor.execute(pipeline, ctx)
