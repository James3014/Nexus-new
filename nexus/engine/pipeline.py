import logging
import time
import json
import subprocess
import sys
import dataclasses
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, Optional
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
    """一次 Pipeline 執行的所有共享狀態"""
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
    # Registry and Tracer (Sprint 13 R15)
    registry: PhaseRegistry = field(default_factory=PhaseRegistry)
    tracer: Any = None
    
    # Legacy handler shortcuts (to be deprecated)
    planner: Any = None
    researcher: Any = None
    repairer: Any = None
    
    # Mutable inter-stage data
    decision_counter: int = 0
    prediction: Any = None
    research_pack: Any = None
    pack: dict = field(default_factory=dict)
    event_store: Any = None  # For R16

class NexusPipeline(
    PipelineStagesMixin, 
    PipelineRepairMixin, 
    PipelineCrystalMixin, 
    PipelineResearchMixin
):
    """⚙️ Nexus Task Pipeline (P-X-D-R-A-C)
    
    IDENTITY: Nexus is a Battlesuit (戰甲), NOT an Agent.
    The AI model wearing Nexus executes tasks through this 6-phase pipeline.
    The learning system belongs to Nexus (the armor), not to any specific model.
    Experience persists across model switches — whoever wears the armor benefits.
    """
    def __init__(self, engine):
        self.engine = engine
        self.registry = PhaseRegistry()
        self._register_default_plugins()

    def _register_default_plugins(self):
        """Registers the standard P-X-R phases as plugins."""
        if not self.engine.phases:
            return
            
        from nexus.engine.phase_plugin import PhasePlugin, PhaseResult

        class _LegacyPhaseAdapter(PhasePlugin):
            def __init__(self, name, handler, pipeline):
                super().__init__(name, priority={"P": 10, "X": 20, "D": 25, "R": 30}.get(name, 100))
                self.handler = handler
                self.pipeline = pipeline

            def should_run(self, ctx):
                if self.name == "X":
                    force = bool(ctx.state.metadata.get("benchmark_force_research"))
                    return force or bool(ctx.state.metadata.get("research_route", {}).get("should_research"))
                return True

            def execute(self, pipeline, ctx) -> PhaseResult:
                # 調用 Pipeline 的內部 _stage_* 方法以保持指標與事件收集
                method_map = {
                    "P": pipeline._stage_plan,
                    "X": pipeline._stage_research,
                    "D": pipeline._stage_diagnose,
                }
                if self.name in method_map:
                    method_map[self.name](ctx, ctx.tracer)
                    return PhaseResult(status="success", mutations={}, events=[])
                
                # 對於 R 階段，由於它是循環的一部分，我們先保持原樣或進行特殊處理
                return PhaseResult(status="skip", mutations={}, events=[])

        # 🛡️ Sprint 15 Logic: 強制 Core 階段映射到 Pipeline Mixins 以維持架構完整性
        core_phases = ["P", "X", "D"]
        for name in core_phases:
            p_handler = self.engine.phases.get(name)
            if p_handler:
                self.registry.register(_LegacyPhaseAdapter(name, p_handler, self))

        # 註冊其餘非核心階段
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
            from nexus.core.handoff_bundle import HandoffBundleWriter
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
                },
            )
        elif ctx.state.metadata.get("pipeline_terminal_state") == "ESCALATED":
            logger.warning("📢 Pipeline 終止於 ESCALATED，Coordinator 應重新規劃")
        return success

    def _run_pipeline_inner(self, task_id: str, trace_id: str, span_id: str, task_desc: str, task_type: str = "bug", context: Optional[Dict] = None, tracer: Any = None, **kwargs) -> bool:
        """執行核心 P-X-D-R-A-C 管線 (Sprint 13 R15 Plugin-driven)"""
        ctx = self._init_pipeline_state(task_id, trace_id, span_id, task_desc, task_type, context, **kwargs)
        ctx.tracer = tracer
        
        # 1. 執行線性階段 (P -> X -> D)
        for plugin in self.registry.get_ordered_plugins():
            if plugin.name in ("P", "X", "D"):
                logger.info("🚀 [Pipeline] Executing Plugin Phase: %s", plugin.name)
                
                from nexus.core.events import NexusEvent
                ctx.event_store.append(NexusEvent(
                    event_id=f"evt_start_{plugin.name}_{int(time.time()*1000)}",
                    task_id=ctx.task_id,
                    phase=plugin.name,
                    event_type="phase_start",
                    payload={"name": plugin.name}
                ))
                
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
                    break 
            
        # 2. 執行複雜循環階段 (R/A)
        success = self._repair_audit_loop(ctx, tracer)
        
        # 3. 執行結晶與結案
        # --- C Stage: Crystallize ---
        self._stage_crystallize(ctx, success, tracer)
        return self._finalize_and_report(ctx, success, tracer)
