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
from nexus.core.event_bus import NexusEventBus
from nexus.core.events import EventStore, NexusEvent
from nexus.telemetry.otel_config import init_otel
from nexus.telemetry.tracer import NexusTracer
from nexus.engine.cli_pregate import run_cli_pregate, _auto_detect_verify_commands
from nexus.learning.cycle_analyzer import analyze_cycle
from nexus.engine.pipeline_outcome import PipelineOutcome, PipelineTerminalState, HumanReviewHandoff
from nexus.core.outcome_schema import NexusOutcomeV2
from nexus.core.handoff_bundle import HandoffBundleWriter
from nexus.engine.phase_plugin import PhaseRegistry, PhasePlugin, PhaseResult

# Mixins 導入
from nexus.engine.pipeline_stages import PipelineStagesMixin
from nexus.engine.pipeline_repair import PipelineRepairMixin
from nexus.engine.pipeline_crystal import PipelineCrystalMixin
from nexus.engine.pipeline_research import PipelineResearchMixin

logger = logging.getLogger(__name__)

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
    pack: dict = field(default_factory=dict)
    event_store: Any = None  # Atomic Sinking (R16)
    outcome_v2: Optional[NexusOutcomeV2] = None

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

    def _register_default_plugins(self):
        """Registers standard phases using the core PHASES_MAP (MUSE-PLUGIN-2.0)."""
        if not hasattr(self.engine, 'phases') or not self.engine.phases:
            return
            
        from nexus.engine.phase_plugin import PhasePlugin, PhaseResult

        class _LegacyPhaseAdapter(PhasePlugin):
            METHOD_MAP = {
                "P": "_stage_plan",
                "X": "_stage_research",
                "D": "_stage_diagnose",
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
                    # 🚀 Pre-Phase Lifecycle Hook
                    ctx.event_store.append(NexusEvent(
                        event_id=f"evt_pre_{self.name}_{int(time.time()*1000)}",
                        task_id=ctx.task_id,
                        phase=self.name,
                        event_type="lifecycle_pre",
                        payload={"nas_aggression": ctx.bayesian_params.get("nas_aggression", 0.0)}
                    ))

                    method = getattr(pipeline, method_name)
                    if self.name == "C":
                        success = ctx.state.metadata.get("pipeline_success", False)
                        method(ctx, success, ctx.tracer)
                    else:
                        method(ctx, ctx.tracer)
                        
                    return PhaseResult(status="success", mutations={}, events=[])
                except Exception as e:
                    logger.error(f"❌ Phase {self.name} failed: {e}", exc_info=True)
                    return PhaseResult(status="FAILED", mutations={}, events=[])

        # 🛡️ Sprint 15 Logic: 強制 Core 階段映射到 Pipeline Mixins 以維持架構完整性
        core_phases = ["P", "X", "D"]
        for name in core_phases:
            p_handler = self.engine.phases.get(name)
            if p_handler:
                self.registry.register(_LegacyPhaseAdapter(name, p_handler, self))

        # 註冊其餘階段（包括 C 結晶階段）
        for name, p_handler in self.engine.phases.items():
            if name in core_phases or not p_handler:
                continue
            
            if isinstance(p_handler, PhasePlugin):
                self.registry.register(p_handler)
            else:
                self.registry.register(_LegacyPhaseAdapter(name, p_handler, self))

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
        if context:
            state.metadata.update(context)
            
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
        return success

    def _run_pipeline_inner(self, task_id: str, trace_id: str, span_id: str, task_desc: str, task_type: str = "bug", context: Optional[Dict] = None, tracer: Any = None, **kwargs) -> bool:
        """執行核心 P-X-D-R-A-C 管線 (Sprint 13 R15 Plugin-driven)"""
        ctx = self._init_pipeline_state(task_id, trace_id, span_id, task_desc, task_type, context, **kwargs)
        ctx.tracer = tracer
        
        success = True
        
        # 1. 執行線性階段 (P -> X -> D)
        for plugin in self.registry.get_ordered_plugins():
            if plugin.name in ("P", "X", "D"):
                if not plugin.should_run(ctx):
                    logger.info("⏩ Skipping phase: %s", plugin.name)
                    continue
                    
                logger.info("🚀 [Pipeline] Executing Plugin Phase: %s", plugin.name)
                
                ctx.event_store.append(NexusEvent(
                    event_id=f"evt_start_{plugin.name}_{int(time.time()*1000)}",
                    task_id=ctx.task_id,
                    phase=plugin.name,
                    event_type="phase_start",
                    payload={"name": plugin.name}
                ))
                
                try:
                    result = plugin.execute(self, ctx)
                    
                    ctx.event_store.append(NexusEvent(
                        event_id=f"evt_end_{plugin.name}_{int(time.time()*1000)}",
                        task_id=ctx.task_id,
                        phase=plugin.name,
                        event_type="phase_end",
                        payload={"status": result.status}
                    ))
                    
                    if result.status == "FAILED":
                        logger.error("❌ Phase %s failed, terminating pipeline.", plugin.name)
                        success = False
                        ctx.state.metadata["pipeline_terminal_state"] = "FAILED"
                        break
                except Exception as e:
                    logger.exception(f"Unhandled failure in plugin {plugin.name}: {e}")
                    success = False
                    ctx.state.metadata["pipeline_terminal_state"] = "FAILED"
                    break
            
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
        ctx.state.metadata["pipeline_success"] = success
        try:
            self._stage_crystallize(ctx, success, tracer)
        except Exception as e:
            logger.error(f"Crystallize stage encountered an error (non-fatal): {e}")
            
        return self._finalize_and_report(ctx, success, tracer)
