import logging
import time
import dataclasses
from typing import Any, Dict, Optional
from nexus.core.protocols import PipelineContextProtocol
from nexus.learning.knowledge_index import KnowledgeIndex
from nexus.core.events import NexusEvent
from nexus.research.research_pack import build_research_pack

logger = logging.getLogger(__name__)

class PipelineStagesMixin:
    """🛤️ Mixin for P-X-D stage methods in NexusPipeline."""
    
    def _register_phase_decision(self, ctx: PipelineContextProtocol, phase: str, skill_id: str) -> str:
        ctx.decision_counter += 1
        decision_id = f"dec_{phase.lower()}_{ctx.task_id}_{ctx.decision_counter}"
        
        # Sprint 13 R16: Event-based decision tracking
        if ctx.event_store:
            event = NexusEvent(
                event_id=f"evt_dec_{int(time.time()*1000)}",
                task_id=ctx.task_id,
                phase=phase,
                event_type="decision",
                payload={"decision_id": decision_id, "skill_id": skill_id}
            )
            ctx.event_store.append(event)
        
        # Legacy backward compatibility sync
        phase_decisions = dict(ctx.state.metadata.get("phase_decisions", {}) or {})
        phase_skills = dict(ctx.state.metadata.get("phase_skills", {}) or {})
        phase_decisions[phase] = decision_id
        phase_skills[phase] = skill_id
        ctx.state.metadata["phase_decisions"] = phase_decisions
        ctx.state.metadata["phase_skills"] = phase_skills
        return decision_id

    def _stage_plan(self, ctx: PipelineContextProtocol, tracer: Any) -> None:
        with tracer.phase_span('P', task_id=ctx.task_id) as p_span:
            # --- P Stage: Plan ---
            ctx.state.current_phase = "P"
            p_decision_id = self._register_phase_decision(ctx, "P", "planner")
            
            try:
                ki = KnowledgeIndex(self.engine.project_root, use_embedding=True)
                p_hints = ki.search_similar(ctx.task_desc, top_k=2, threshold=0.2, task_type=ctx.task_type)
                strategies = [fm.plan_strategy for fm, _ in p_hints if fm.plan_strategy]
                if strategies:
                    ctx.kwargs["plan_hint"] = f"歷史成功策略: {strategies[0]}"
                    ctx.state.metadata["inherited_plan_strategy"] = strategies[0]
                    logger.info("📋 P 階段：繼承歷史策略 → %s", strategies[0])
            except (ImportError, FileNotFoundError, Exception) as exc:
                logger.debug("p_phase_learning_skip: %s", exc)

            decision = ctx.hub.make_pre_routing_decision(ctx.task_id, {"type": ctx.task_type, **(ctx.state.metadata or {})})
            ctx.prediction = ctx.planner.run(ctx.state, {"task": ctx.task_desc, **ctx.kwargs})
            ctx.accumulator.record(ctx.state, "P", ctx.prediction)
            self.engine._add_step_to_history(
                ctx.state, "P", metadata={"prediction": ctx.prediction, "decision_id": p_decision_id, "skill_id": "planner"}
            )

    def _stage_research(self, ctx: PipelineContextProtocol, tracer: Any) -> None:
        import json
        with tracer.phase_span('X', task_id=ctx.task_id) as x_span:
            # --- X Stage: Research ---
            force_research = bool(ctx.state.metadata.get("benchmark_force_research"))
            decision = ctx.hub.make_pre_routing_decision(ctx.task_id, {"type": ctx.task_type, **(ctx.state.metadata or {})})
            res_decision = ctx.research_policy.route(
                decision, ctx.task_desc, task_type=ctx.task_type, prediction=ctx.prediction, context=ctx.state.metadata
            )
            ctx.state.metadata["research_route"] = dataclasses.asdict(res_decision) if dataclasses.is_dataclass(res_decision) else {}
            
            if not ctx.dry_run and (force_research or res_decision.should_research):
                ctx.state.current_phase = "X"
                x_decision_id = self._register_phase_decision(ctx, "X", "researcher")
                self._gather_research_hints(ctx)

                if res_decision.mode == "experimental" and ctx.state.metadata.get("research_workspace"):
                    ctx.research_pack = self._run_experimental_phase(ctx, res_decision)
                else:
                    ctx.research_pack = self._run_standard_phase(ctx, res_decision)
                
                self._persist_research_pack(ctx, x_decision_id)

    def _gather_research_hints(self, ctx: PipelineContextProtocol):
        try:
            ki = KnowledgeIndex(self.engine.project_root, use_embedding=True)
            x_hints = ki.search_similar(ctx.task_desc, top_k=2, threshold=0.3, task_type=ctx.task_type)
            prior = [fm.winning_hypothesis for fm, _ in x_hints if fm.winning_hypothesis]
            if prior:
                ctx.state.metadata["prior_winning_hypotheses"] = prior
                logger.info("🔬 X 階段：找到 %d 個歷史勝出假設", len(prior))
        except Exception as exc:
            logger.debug("x_phase_learning_skip: %s", exc)

    def _run_experimental_phase(self, ctx: PipelineContextProtocol, res_decision: Any) -> Dict[str, Any]:
        return self._run_experimental_research(
            task_id=ctx.task_id, task_desc=ctx.task_desc, 
            workspace=str(ctx.state.metadata.get("research_workspace")),
            rounds=max(int(ctx.state.metadata.get("research_rounds", res_decision.rounds) or 0), 1),
            stable_wins=max(int(ctx.state.metadata.get("research_stable_wins", res_decision.stable_wins) or 0), 1),
            proof_ratio_min=float(ctx.state.metadata.get("research_proof_ratio_min", 95.0) or 95.0)
        )

    def _run_standard_phase(self, ctx: PipelineContextProtocol, res_decision: Any) -> Dict[str, Any]:
        from nexus.research.research_pack import ResearchContext
        legacy_pack = ctx.researcher.run(ctx.state, {"task": ctx.task_desc})
        res_ctx = ResearchContext(
            task=ctx.task_desc, mode="external", source=str(legacy_pack.get("source", "INTERNAL")),
            reason=res_decision.reason, status=str(legacy_pack.get("status", "FAIL")),
            findings=list(legacy_pack.get("findings", []) or []),
            raw=legacy_pack, rounds=res_decision.rounds, time_sec=0.0
        )
        return build_research_pack(res_ctx)

    def _persist_research_pack(self, ctx: PipelineContextProtocol, decision_id: str):
        import json
        try:
            research_path = self.engine.run_dir / "research_pack.json"
            research_path.write_text(json.dumps(ctx.research_pack, ensure_ascii=False, indent=2), encoding="utf-8")
            ctx.state.metadata["research_pack_path"] = str(research_path)
        except Exception as exc:
            logger.warning("research_pack_write_failed: %s", exc)
        ctx.accumulator.record(ctx.state, "X", ctx.research_pack, overhead=50)
        self.engine._add_step_to_history(
            ctx.state, "X", metadata={**ctx.research_pack, "decision_id": decision_id, "skill_id": "researcher"}
        )

    def _stage_diagnose(self, ctx: PipelineContextProtocol, tracer: Any) -> None:
        with tracer.phase_span('D', task_id=ctx.task_id) as d_span:
            # --- D Stage: Diagnose ---
            ctx.state.current_phase = "D"
            d_decision_id = self._register_phase_decision(ctx, "D", "diagnose-pack")
            
            if ctx.task_id and ctx.task_type == "bug":
                ctx.pack = ctx.hub.assemble_diag_pack([], ctx.task_desc)
            else:
                ctx.pack = ctx.hub.assemble_feature_pack(plan=ctx.prediction)

            if ctx.research_pack:
                ctx.pack["research_context"] = ctx.research_pack
                ctx.pack["research_pack"] = ctx.research_pack

            self._match_learned_skills(ctx)
            self._apply_cycle_prevention_logic(ctx)
            
            self.engine._add_step_to_history(
                ctx.state, "D", metadata={"pack_keys": list(ctx.pack.keys()), "decision_id": d_decision_id, "skill_id": "diagnose-pack"}
            )

    def _match_learned_skills(self, ctx: PipelineContextProtocol):
        try:
            ki = KnowledgeIndex(self.engine.project_root, use_embedding=True)
            similar = ki.search_similar(ctx.task_desc, top_k=3, threshold=0.1, task_type=ctx.task_type)
            if similar:
                ctx.pack["learned_skills"] = [
                    {
                        "name": fm.name, "description": fm.description[:200], "task_type": fm.task_type,
                        "keywords": fm.keywords[:5], "score": round(score, 3), "skill_id": fm.task_id,
                        "plan_strategy": fm.plan_strategy, "winning_hypothesis": fm.winning_hypothesis,
                        "phantom_patterns": fm.phantom_patterns, "cycle_count": fm.cycle_count,
                        "cycle_root_cause": fm.cycle_root_cause, "verification_commands": fm.verification_commands,
                    }
                    for fm, score in similar
                ]
                ctx.state.metadata["matched_skills_count"] = len(similar)
                logger.info("🧠 Found %d similar learned skills", len(similar))
                self._handle_embedding_version_mismatch(ctx, ki)
        except Exception as skill_exc:
            logger.warning("learned_skill_lookup_failed: %s", skill_exc)

    def _handle_embedding_version_mismatch(self, ctx: PipelineContextProtocol, ki: Any):
        if ki._cache:
            current_ver = ki._cache.model_version
            for skill_dict in ctx.pack.get("learned_skills", []):
                if skill_dict.get("embedding_model_version") and skill_dict["embedding_model_version"] != current_ver:
                    skill_dict["_embedding_version_mismatch"] = True
                    skill_dict["score"] = round(skill_dict["score"] * 0.5, 3)
                    logger.warning("⚠️ Embedding mismatch for %s, de-weighted.", skill_dict["skill_id"])

    def _apply_cycle_prevention_logic(self, ctx: PipelineContextProtocol):
        try:
            learned = ctx.pack.get("learned_skills", [])
            if learned:
                best = learned[0]
                if best.get("cycle_root_cause") == "phantom_proof":
                    ctx.pack["enforce_physical_proof"] = True
                    logger.info("🔄 歷史循環根因=phantom_proof，強制要求物理證明")
                elif best.get("cycle_root_cause") == "insufficient_diag":
                    ctx.pack["force_deep_diagnosis"] = True
                    logger.info("🔄 歷史循環根因=insufficient_diag，強制深度診斷")
        except Exception as exc:
            logger.debug("r_phase_cycle_prevention_skip: %s", exc)
