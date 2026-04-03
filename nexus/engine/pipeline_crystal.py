from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import logging
import dataclasses
import os
import subprocess
from datetime import datetime, timezone
from nexus.core.protocols import PipelineContextProtocol
from nexus.learning.cycle_analyzer import analyze_cycle
from nexus.learning.skill_artifact import build_skill_artifact
from nexus.learning.skill_store import SkillStore
from nexus.learning.skill_exchange import SkillExchange
from nexus.learning.skill_registry import SkillRegistry
from nexus.core.skill_outcomes import build_outcome_event, append_skill_outcome_event
from nexus.core.event_bus import NexusEventBus
from nexus.engine.pipeline_outcome import PipelineOutcome, PipelineTerminalState, HumanReviewHandoff
from nexus.core.outcome_schema import NexusOutcomeV2
from nexus.services.continuous_learning import finalize_learning_loop

logger = logging.getLogger(__name__)

class PipelineCrystalMixin:
    """💎 Mixin for Crystallize stage methods in NexusPipeline."""
    
    def _stage_crystallize(self, ctx: PipelineContextProtocol, success: bool, tracer: Any) -> None:
        """主入口：執行 C 階段結晶邏輯。"""
        signals = self._collect_crystal_signals(ctx, success, tracer)
        
        # 🔧 FIX: 先觸發 LearningScorer 計算 pattern_reuse_rate / next_run_hit_rate，
        # 再寫入 outcome event，否則 learning signal 永遠為 0.0。
        try:
            from nexus.core.learning_evidence import LearningEvidenceBuilder
            from nexus.core.learning_scorer import LearningScorer
            evidence = LearningEvidenceBuilder.build(ctx.state)
            LearningScorer.apply(ctx.state, evidence)
        except Exception as exc:
            logger.warning("pre_crystallize_learning_score_failed: %s", exc)
        
        if success:
            self._handle_crystallize_success(ctx, signals)
        else:
            self._handle_crystallize_failure(ctx)

        learning_finalize = None
        try:
            learning_finalize = finalize_learning_loop(
                getattr(self.engine, "project_root", Path(".")),
                ctx.state,
                success=success,
                source="pipeline.crystallize",
            )
        except Exception as exc:
            logger.warning("continuous_learning_finalize_failed: %s", exc)
            
        self.engine.state_io.save_global_state(ctx.state)
        next_status = "completed"
        if isinstance(learning_finalize, dict) and learning_finalize.get("writeback_required"):
            next_status = "pending_writeback"
        self.engine.commander.next_step(status=next_status, state=ctx.state)

    def _collect_crystal_signals(self, ctx: PipelineContextProtocol, success: bool, tracer: Any) -> dict:
        """收集結晶所需的信號與元數據。"""
        with tracer.phase_span('C', task_id=ctx.task_id) as c_span:
            # --- C Stage: Crystallize ---
            escalation_triggered = bool(ctx.state.metadata.get("escalation_triggered"))
            human_review = bool(ctx.state.metadata.get("human_review_required"))
            ctx.state.metadata["pipeline_success"] = bool(success)
            
            raw_terminal_state = (
                "HUMAN_REVIEW" if human_review
                else "ESCALATED" if escalation_triggered
                else "SUCCESS" if success
                else "FAILED"
            )
            ctx.state.metadata["pipeline_terminal_state"] = raw_terminal_state
        
        handoff = None
        if human_review:
            handoff = HumanReviewHandoff(
                escalation_count=int(ctx.state.metadata.get("escalation_count", 0)),
                last_root_cause=ctx.state.metadata.get("human_review_reason") or str(ctx.state.metadata.get("cycle_root_cause", "")),
                rejection_history=list(ctx.state.metadata.get("rejection_history", [])),
                sandbox_mode=ctx.state.metadata.get("sandbox_mode", "unknown"),
                pregate_skip_reason=ctx.state.metadata.get("pregate_skip_reason", ""),
                task_id=ctx.state.task_id,
                trace_id=ctx.state.metadata.get("trace_id", ""),
                terminal_state="HUMAN_REVIEW"
            )
        
        outcome = PipelineOutcome(
            terminal_state=PipelineTerminalState[raw_terminal_state],
            exit_code=PipelineTerminalState[raw_terminal_state].value,
            task_id=ctx.state.task_id,
            trace_id=ctx.state.metadata.get("trace_id", ""),
            handoff=handoff,
            cycle_root_cause=str(ctx.state.metadata.get("cycle_root_cause", "")),
            verification_exit_codes=list(ctx.state.metadata.get("verification_exit_codes", [])),
            sandbox_mode=ctx.state.metadata.get("sandbox_mode", "unknown"),
            pregate_skip=bool(ctx.state.metadata.get("pregate_skip", False))
        )
        
        ctx.state.metadata["pipeline_outcome"] = dataclasses.asdict(outcome)

        try:
            cycle = analyze_cycle(ctx.state.metadata.get("rejection_history", []))
            ctx.state.metadata["cycle_root_cause"] = cycle["root_cause"]
            ctx.state.metadata["cycle_analysis"] = cycle
        except (ValueError, TypeError, KeyError) as exc:
            logger.debug("c_phase_cycle_analysis_failed: %s", exc)

        ctx.state.metadata["plan_strategy_used"] = ctx.state.metadata.get("inherited_plan_strategy", "")

        phantom_history = list(ctx.state.metadata.get("known_phantom_patterns", []))
        if ctx.state.metadata.get("phantom_success_reason"):
            phantom_history.append(ctx.state.metadata["phantom_success_reason"])
        ctx.state.metadata["phantom_pattern_history"] = list(set(phantom_history))
        
        commit_sha = "unknown"
        try:
            commit_sha = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=str(self.engine.project_root), stderr=subprocess.DEVNULL
            ).decode().strip()
        except (subprocess.CalledProcessError, OSError, FileNotFoundError):
            import logging
            logging.getLogger(__name__).debug("git_rev_parse_failed: workspace might not be a git repo")
            
        outcome_v2 = NexusOutcomeV2(
            task_id=ctx.state.task_id,
            trace_id=ctx.state.metadata.get("trace_id", ""),
            span_id=ctx.state.metadata.get("span_id", ""),
            terminal_state=raw_terminal_state,
            exit_code=PipelineTerminalState[raw_terminal_state].value,
            sandbox_mode=ctx.state.metadata.get("sandbox_mode", "unknown"),
            pregate_skip=bool(ctx.state.metadata.get("pregate_skip", False)),
            pregate_skip_reason=ctx.state.metadata.get("pregate_skip_reason", ""),
            trust_level="production" if success else "untrusted",
            escalation_count=int(ctx.state.metadata.get("escalation_count", 0)),
            verification_commands=list(ctx.state.metadata.get("verification_commands", [])),
            verification_exit_codes=list(ctx.state.metadata.get("verification_exit_codes", [])),
            cycle_root_cause=str(ctx.state.metadata.get("cycle_root_cause", "")),
            rejection_history=list(ctx.state.metadata.get("rejection_history", [])),
            phantom_patterns=list(set(phantom_history)),
            commit_sha=commit_sha,
            model_version=os.environ.get("NEXUS_MODEL", "unknown"),
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        
        ctx.state.metadata["nexus_outcome_v2"] = dataclasses.asdict(outcome_v2)
        return {
            "raw_terminal_state": raw_terminal_state,
            "phantom_history": phantom_history,
            "outcome_v2": outcome_v2
        }

    def _handle_crystallize_success(self, ctx: PipelineContextProtocol, signals: dict) -> None:
        """處理成功的結晶（構建 Skill）。"""
        ctx.state.current_phase = "C"
        c_decision_id = self._register_phase_decision(ctx, "C", "crystallize")
        self.engine._add_step_to_history(
            ctx.state, "C", metadata={"decision_id": c_decision_id, "skill_id": "crystallize"}
        )
        
        try:
            from nexus.core.skill_outcomes import OutcomePayload
            payload = OutcomePayload(
                task_id=ctx.state.task_id,
                phase="C",
                decision_id=c_decision_id,
                skill_id="crystallize",
                passed=True,
                phantom_blocked=False,
                repair_success=True,
                retry_count=max(0, ctx.state.retry_count),
                proof_present=bool(
                    str(ctx.state.metadata.get("last_proof_type", "") or "")
                    and str(ctx.state.metadata.get("last_proof_value", "") or "")
                ),
                regression_pass_rate=100.0,
                pattern_reuse=float(ctx.state.metadata.get("pattern_reuse_rate", 0.0) or 0.0),
                next_run_hit=float(ctx.state.metadata.get("next_run_hit_rate", 0.0) or 0.0),
                metadata={"status": "COMPLETED", "audit_status": "APPROVED", "source": "pipeline.crystallize"},
            )
            c_event = build_outcome_event(payload)
            root_path = Path(getattr(self.engine, "project_root", ".")) if hasattr(self, "engine") else Path(".")
            print(f"DEBUG: writing outcome event to {root_path.resolve()}")
            append_skill_outcome_event(root_path, c_event)
            self._build_and_share_skill(ctx, c_event)


        except (OSError, RuntimeError, ValueError) as exc:
            logger.warning("skill_outcome_event_write_failed: %s", exc)

    def _build_and_share_skill(self, ctx: PipelineContextProtocol, c_event: Any) -> None:
        """構建 SkillArtifact 並同步到註冊表。"""
        try:
            if hasattr(c_event, "to_dict"):
                outcome_dict = c_event.to_dict()
            elif dataclasses.is_dataclass(c_event):
                outcome_dict = dataclasses.asdict(c_event)
            elif hasattr(c_event, "__dict__"):
                outcome_dict = vars(c_event)
            else:
                outcome_dict = {}
            outcome_dict["verification_commands"] = ctx.state.metadata.get("verification_commands", [])
            outcome_dict["verification_exit_codes"] = ctx.state.metadata.get("verification_exit_codes", [])
            outcome_dict["pregate_skip"] = ctx.state.metadata.get("pregate_skip", False)
            outcome_dict["pregate_skip_reason"] = ctx.state.metadata.get("pregate_skip_reason", "")
            outcome_dict["sandbox_mode"] = ctx.state.metadata.get("sandbox_mode", "unknown")
            
            research_pack = ctx.state.metadata.get("research_pack")
            repair_result = ctx.state.metadata.get("repair_result", {})

            skill_md = build_skill_artifact(
                task_id=ctx.state.task_id,
                task_desc=getattr(ctx.state, "task_desc", ctx.state.task_id),
                research_pack=research_pack,
                repair_result=repair_result,
                outcome_event=outcome_dict
            )

            if skill_md:
                store = SkillStore(self.engine.project_root)
                store.save_skill(ctx.state.task_id, skill_md)
                ctx.state.metadata["generated_skill_path"] = str(self.engine.project_root / "skills" / "learned" / f"{ctx.state.task_id}.md")
                logger.info("✨ Generated skill artifact: %s", f"{ctx.state.task_id}.md")
                NexusEventBus.publish("skill_created", {"task_id": ctx.state.task_id, "skill_path": ctx.state.metadata["generated_skill_path"]})
                
                self._share_skill_to_registry(ctx)
        except (ValueError, TypeError, OSError) as artifact_exc:
            logger.warning("skill_artifact_generation_failed: %s", artifact_exc)

    def _share_skill_to_registry(self, ctx: PipelineContextProtocol) -> None:
        """將 Skill 分享到聯邦註冊表。"""
        try:
            enabled = os.environ.get("NEXUS_SKILL_SHARE_ENABLED", "1")
            if enabled == "1":
                exchange = SkillExchange(
                    store=SkillStore(self.engine.project_root),
                    registry=SkillRegistry(
                        self.engine.project_root / ".nexus" / "registry" / "shared_skills.db"
                    )
                )
                pushed = exchange.push_local_to_registry(
                    task_id=ctx.state.task_id,
                    node_id=os.environ.get("NEXUS_NODE_ID", "local"),
                )
                if pushed:
                    NexusEventBus.publish("skill_shared", {"task_id": ctx.state.task_id, "registry_path": str(exchange.registry.db_path)})
        except (OSError, ConnectionError, RuntimeError, ValueError) as share_exc:
            logger.warning("skill_push_failed: %s", share_exc)

    def _handle_crystallize_failure(self, ctx: PipelineContextProtocol) -> None:
        """處理失敗的結晶。"""
        try:
            from nexus.core.skill_outcomes import OutcomePayload
            fail_decision_id = self._register_phase_decision(ctx, "C", "crystallize")
            payload = OutcomePayload(
                task_id=ctx.state.task_id, 
                phase="C", 
                decision_id=fail_decision_id, 
                skill_id="crystallize", 
                passed=False, 
                phantom_blocked=bool(ctx.state.metadata.get("phantom_success_reason")), 
                repair_success=False, 
                retry_count=max(0, ctx.state.retry_count), 
                proof_present=bool(str(ctx.state.metadata.get("last_proof_type", "") or "") and str(ctx.state.metadata.get("last_proof_value", "") or "")), 
                regression_pass_rate=0.0, 
                pattern_reuse=float(ctx.state.metadata.get("pattern_reuse_rate", 0.0) or 0.0), 
                next_run_hit=float(ctx.state.metadata.get("next_run_hit_rate", 0.0) or 0.0), 
                metadata={"status": "FAILED", "audit_status": "REJECTED", "source": "pipeline.crystallize"}
            )
            fail_event = build_outcome_event(payload)
            root_path = Path(getattr(self.engine, "project_root", ".")) if hasattr(self, "engine") else Path(".")
            append_skill_outcome_event(root_path, fail_event)
        except (OSError, RuntimeError, ValueError) as exc:
            logger.warning("skill_outcome_event_write_failed: %s", exc)
