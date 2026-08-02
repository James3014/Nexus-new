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
from nexus.events.contracts import (
    NexusEvent,
    build_lifecycle_hook_event,
    build_phase_observer_event,
    build_phase_transition_event,
)
from nexus.telemetry.otel_config import init_otel
from nexus.telemetry.tracer import NexusTracer
from nexus.engine.cli_pregate import run_cli_pregate, _auto_detect_verify_commands
from nexus.learning.cycle_analyzer import analyze_cycle
from nexus.engine.pipeline_outcome import PipelineOutcome, PipelineTerminalState, HumanReviewHandoff
from nexus.core.outcome_schema import NexusOutcomeV2
from nexus.core.handoff_bundle import HandoffBundleWriter
from nexus.core.blackboard import Blackboard
from nexus.engine.phase_plugin import PhaseRegistry, PhasePlugin, PhaseResult, PhaseExecutor
from nexus.engine.phase_handshake import (
    build_phase_receipt,
    record_phase_artifacts,
    validate_phase_receipt,
    validate_required_artifacts,
)
from nexus.engine.runtime_phase_contract import (
    RUNTIME_PHASE_FLOW,
    RuntimePhase,
    RuntimeStatus,
    validate_transition,
)

# Mixins 導入
from nexus.engine.pipeline_stages import PipelineStagesMixin
from nexus.engine.pipeline_repair import PipelineRepairMixin
from nexus.engine.pipeline_crystal import PipelineCrystalMixin
from nexus.engine.pipeline_research import PipelineResearchMixin

logger = logging.getLogger(__name__)
CANONICAL_STAGE_FLOW = [phase.value for phase in RUNTIME_PHASE_FLOW]
STAGE_DESCRIPTIONS = {
    "S": "cold_start_seed",
    "P": "plan",
    "D": "diagnose",
    "X": "research_xray",
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
    blackboard: Blackboard = field(default_factory=Blackboard)
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
        self.blackboard.append(origin_phase, event_type, event)
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
    
    PHASE_PRIORITY_MAP = {"P": 10, "D": 20, "X": 30, "R": 40, "A": 50, "C": 60}

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

    def _advance_runtime_phase(
        self,
        ctx: PipelineContext,
        destination: RuntimePhase | RuntimeStatus | str,
        *,
        audit_passed: bool | None = None,
        reason: str = "",
    ) -> tuple[RuntimePhase, RuntimePhase | RuntimeStatus]:
        """Guard one runtime transition before a phase executor is called."""

        source_value = str(ctx.state.metadata.get("runtime_phase") or RuntimePhase.S.value)
        source, target = validate_transition(
            source_value,
            destination,
            audit_passed=audit_passed,
        )
        receipt = {
            "from": source.value,
            "to": target.value,
            "reason": reason or "phase_entry",
        }
        ctx.state.metadata.setdefault("runtime_phase_transitions", []).append(receipt)
        if isinstance(target, RuntimePhase):
            ctx.state.metadata["runtime_phase"] = target.value
            ctx.state.current_phase = target.value
        else:
            ctx.state.metadata["runtime_status"] = target.value
        return source, target

    def _emit_phase_observer(self, ctx: PipelineContext, phase: str, hook: str, **payload: Any) -> None:
        """Emit telemetry hooks without allowing observers to change authority."""

        try:
            ctx.event_store.append(
                build_phase_observer_event(
                    task_id=ctx.task_id,
                    phase=phase,
                    hook=hook,
                    payload=payload,
                )
            )
        except Exception as exc:  # observer telemetry is explicitly fail-open
            logger.debug("phase_observer_failed hook=%s phase=%s: %s", hook, phase, exc)

    def _record_phase_receipt(
        self,
        ctx: PipelineContext,
        *,
        phase: str,
        status: str,
        transition: str,
        output_payload: Any,
        block_class: str = "",
        next_action: str = "",
    ) -> dict[str, Any]:
        attempts = ctx.state.metadata.setdefault("phase_attempts", {})
        phase_attempt = int(attempts.get(phase, 0)) + 1
        attempts[phase] = phase_attempt
        receipt = build_phase_receipt(
            task_id=ctx.task_id,
            attempt_id=str(ctx.state.metadata.get("attempt_id") or f"{ctx.task_id}:attempt"),
            action_id=str(ctx.state.metadata.get("action_id") or f"{ctx.task_id}:{phase}"),
            phase=phase,
            phase_attempt=phase_attempt,
            input_payload={"task_id": ctx.task_id, "phase": phase, "attempt": phase_attempt},
            output_payload=output_payload,
            authority_revision=str(
                ctx.state.metadata.get("authority_revision")
                or ctx.state.metadata.get("workspace_revision")
                or "runtime-phase-contract-v1"
            ),
            status=status,
            transition=transition,
            evidence_refs=tuple(ctx.state.metadata.get("evidence_refs") or ()),
            verifier_refs=tuple(ctx.state.metadata.get("verifier_refs") or ()),
            timeout_telemetry=dict(ctx.state.metadata.get("timeout_telemetry") or {}),
            block_class=block_class,
            next_action=next_action,
        )
        validate_phase_receipt(receipt)
        ctx.state.metadata.setdefault("phase_receipts", []).append(receipt)
        return receipt

    @staticmethod
    def _formulation_phase_order(plugins: dict[str, PhasePlugin], ctx: PipelineContext) -> list[str]:
        """Return P→D with optional X; the caller records X→D resume."""

        order = ["P", "D"]
        research = plugins.get("X")
        if research is not None and research.should_run(ctx):
            order.append("X")
        return order

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

        # Core task phases are composition-only. Executor bootstrap failures must
        # remain visible instead of silently falling back to mixin methods.
        core_phases: list[str] = []
        composition_only_phases = {"P", "X", "D"}
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
            from nexus.engine.phase_factory import PhaseFactory

            return PhaseFactory(project_root=Path(project_root), run_dir=Path(run_dir), hub=getattr(self.engine, "hub", None)).create_all()
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
        if success and ctx.state.metadata.get("runtime_phase") == RuntimePhase.A.value:
            self._advance_runtime_phase(ctx, RuntimePhase.C, audit_passed=True, reason="audit_passed_crystallize_entry")
        plugin = next((item for item in self.registry.get_ordered_plugins() if item.name == "C"), None)
        if plugin is not None and plugin.should_run(ctx):
            self._emit_phase_observer(ctx, "C", "on_phase_start")
            result = plugin.execute(self, ctx)
            mutations = dict(getattr(result, "mutations", None) or {})
            ctx.state.metadata["composition_crystallize_phase_status"] = str(getattr(result, "status", ""))
            ctx.state.metadata["composition_crystallize_phase_mutations"] = mutations
            self._record_phase_receipt(
                ctx,
                phase="C",
                status=str(getattr(result, "status", "FAILED")),
                transition="C:start->end",
                output_payload=mutations,
                next_action="terminal_outcome",
            )
            self._emit_phase_observer(ctx, "C", "on_phase_end", status=str(getattr(result, "status", "")))
            if self._crystallize_side_effects_present(ctx):
                ctx.state.metadata["composition_crystallize_side_effects_verified"] = True
                return
            self._emit_phase_observer(ctx, "C", "on_phase_fail", reason="missing_terminal_outcome_side_effects")
            ctx.state.metadata["composition_crystallize_side_effects_verified"] = False
            ctx.state.metadata["composition_crystallize_failure_reason"] = "missing_terminal_outcome_side_effects"
            ctx.state.metadata["pipeline_terminal_state"] = "FAILED"
            return
        ctx.state.metadata["composition_crystallize_phase_status"] = "MISSING"
        self._emit_phase_observer(ctx, "C", "on_phase_block", reason="missing_crystallize_executor")
        ctx.state.metadata["composition_crystallize_failure_reason"] = "missing_crystallize_executor"
        ctx.state.metadata["pipeline_terminal_state"] = "FAILED"

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
        state.metadata.setdefault("runtime_phase", RuntimePhase.S.value)
        state.metadata.setdefault("runtime_phase_transitions", [])
            
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

    def _run_formulation_plugin(self, plugin: PhasePlugin, ctx: PipelineContext) -> bool:
        """Run one P/D/X plugin after the contract gate accepts its entry."""

        self._advance_runtime_phase(ctx, plugin.name, reason="formulation_phase_entry")
        self._emit_phase_observer(ctx, plugin.name, "on_phase_start")
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
            validate_required_artifacts(phase=plugin, blackboard=ctx.blackboard)
            result = plugin.execute(self, ctx)
            record_phase_artifacts(phase=plugin, result=result, blackboard=ctx.blackboard)
            ctx.event_store.append(
                build_phase_transition_event(
                    task_id=ctx.task_id,
                    phase=plugin.name,
                    transition="end",
                    payload={"status": result.status},
                )
            )
            self._record_phase_receipt(
                ctx,
                phase=plugin.name,
                status=result.status,
                transition=f"{plugin.name}:start->end",
                output_payload=result.mutations,
            )
            self._emit_phase_observer(ctx, plugin.name, "on_phase_end", status=result.status)
            if result.status in {"FAILED", "fail"}:
                logger.error("❌ Phase %s failed, terminating pipeline.", plugin.name)
                self._emit_phase_observer(ctx, plugin.name, "on_phase_fail", status=result.status)
                ctx.state.metadata["pipeline_terminal_state"] = "FAILED"
                return False
            return True
        except RuntimeError as veto_err:
            veto_str = str(veto_err)
            if veto_str.startswith("SEMANTIC_HANDSHAKE_MISSING_ARTIFACT"):
                logger.error("🛑 [Pipeline] Semantic handshake failed: %s", veto_err)
                self._emit_phase_observer(ctx, plugin.name, "on_phase_block", reason=veto_str)
                ctx.state.metadata["pipeline_terminal_state"] = "FAILED"
                ctx.state.metadata["semantic_handshake_failed"] = True
                ctx.state.metadata["semantic_handshake_reason"] = veto_str
                return False
            raise
        except Exception as exc:
            logger.exception("Unhandled failure in plugin %s: %s", plugin.name, exc)
            self._emit_phase_observer(ctx, plugin.name, "on_phase_fail", reason=str(exc))
            ctx.state.metadata["pipeline_terminal_state"] = "FAILED"
            return False

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
        
        # 1. Execute the contract order P -> D -> X -> D (optional X).
        pxd_attempts = 0
        MAX_PXD_RETRIES = 2
        
        while pxd_attempts < MAX_PXD_RETRIES and success:
            pxd_attempts += 1
            pxd_veto = False
            executed_formulation_phases: list[str] = []
            
            is_direct_mode = bool(ctx.state.metadata.get("direct_mode", False))
            if is_direct_mode:
                logger.info("⚡ [Pipeline] Direct Mode active: Bypassing formulation executors.")
                self._advance_runtime_phase(ctx, RuntimePhase.P, reason="direct_mode_virtual_plan")
                self._advance_runtime_phase(ctx, RuntimePhase.D, reason="direct_mode_virtual_diagnose")
                break
            plugins = {plugin.name: plugin for plugin in self.registry.get_ordered_plugins()}
            for phase_name in ("P", "D"):
                plugin = plugins.get(phase_name)
                if plugin is None or not plugin.should_run(ctx):
                    logger.info("⏩ Skipping phase: %s", phase_name)
                    continue

                executed_formulation_phases.append(plugin.name)
                if not self._run_formulation_plugin(plugin, ctx):
                    success = False
                    break
                if False:  # legacy inline executor path retained for history
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
                        validate_required_artifacts(phase=plugin, blackboard=ctx.blackboard)
                        result = plugin.execute(self, ctx)
                        record_phase_artifacts(phase=plugin, result=result, blackboard=ctx.blackboard)
                        
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
                        if veto_str.startswith("SEMANTIC_HANDSHAKE_MISSING_ARTIFACT"):
                            logger.error("🛑 [Pipeline] Semantic handshake failed: %s", veto_err)
                            success = False
                            ctx.state.metadata["pipeline_terminal_state"] = "FAILED"
                            ctx.state.metadata["semantic_handshake_failed"] = True
                            ctx.state.metadata["semantic_handshake_reason"] = veto_str
                            break
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
            
            if not pxd_veto and success:
                research_plugin = plugins.get("X")
                if research_plugin is not None and research_plugin.should_run(ctx):
                    executed_formulation_phases.append("X")
                    if not self._run_formulation_plugin(research_plugin, ctx):
                        success = False
                    else:
                        # X returns control to the same D phase. The
                        # continuation is a guarded state boundary; D's
                        # executor remains single-run for compatibility.
                        self._advance_runtime_phase(ctx, RuntimePhase.D, reason="research_resume_boundary")

            if not pxd_veto:
                break  # P-D-X-D 全部通過或 terminal failure，跳出
            
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

    def required_artifacts(self) -> tuple[str, ...]:
        provider = getattr(self.executor, "required_artifacts", None)
        return tuple(provider() or ()) if callable(provider) else ()

    def provided_artifacts(self) -> tuple[str, ...]:
        provider = getattr(self.executor, "provided_artifacts", None)
        return tuple(provider() or ()) if callable(provider) else ()
