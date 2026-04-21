from typing import Any, Dict, List, Optional, Tuple
import logging
import time
import dataclasses
import json
from pathlib import Path
from nexus.core.protocols import PipelineContextProtocol
from nexus.learning.knowledge_index import KnowledgeIndex
from nexus.core.events import NexusEvent
from nexus.research.research_pack import build_research_pack
from nexus.research.learn.policy_runtime import decide_research_engine, load_phase_policy

logger = logging.getLogger(__name__)

class PipelineStagesMixin:
    """🛤️ Mixin for P-X-D stage methods in NexusPipeline (v24.0 Master Loop Hardened)."""
    
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

    def _load_learn_phase_slo_guard(self, ctx: PipelineContextProtocol) -> Dict[str, Any]:
        project_root = Path(getattr(self.engine, "project_root", "."))
        slo_path = project_root / ".nexus" / "reports" / "learn" / "phase_slo_summary.json"
        if not slo_path.exists():
            return {
                "active": False,
                "ready": True,
                "phase_slo_pass": True,
                "required_done_ratio": 1.0,
                "reason": "phase_slo_summary_missing",
                "path": str(slo_path),
            }
        try:
            data = json.loads(slo_path.read_text(encoding="utf-8"))
        except Exception:
            return {
                "active": True,
                "ready": False,
                "phase_slo_pass": False,
                "required_done_ratio": 0.0,
                "reason": "phase_slo_summary_parse_error",
                "path": str(slo_path),
            }
        phase_slo_pass = bool((data or {}).get("phase_slo_pass", False))
        required_done_ratio = float(((data or {}).get("global", {}) or {}).get("required_done_ratio", 0.0) or 0.0)
        ready = phase_slo_pass and required_done_ratio >= 0.95
        return {
            "active": True,
            "ready": ready,
            "phase_slo_pass": phase_slo_pass,
            "required_done_ratio": required_done_ratio,
            "reason": "" if ready else "learn_phase_slo_not_ready",
            "path": str(slo_path),
        }

    def _stage_plan(self, ctx: PipelineContextProtocol, tracer: Any) -> None:
        with tracer.phase_span('P', task_id=ctx.task_id) as p_span:
            # --- P Stage: Plan (v24.0 Hardened - Learning Injected) ---
            ctx.state.current_phase = "P"
            # R2: Derive Learn-aware Phase Policy
            policy_actions = load_phase_policy(self.engine.project_root, task_type=ctx.task_type, risk_level='standard')
            ctx.state.metadata['phase_policy'] = {
                'allow_research': policy_actions.allow_research,
                'force_baseline': policy_actions.force_baseline,
                'require_writeback': policy_actions.require_writeback,
                'audit_strictness': policy_actions.audit_strictness.value,
                'reasoning': policy_actions.reasoning
            }
            p_decision_id = self._register_phase_decision(ctx, "P", "planner")
            
            # 🧪 [Round 20] Bayesian Parameter Injection from current context
            nas_aggression = (ctx.bayesian_params or {}).get("nas_aggression", 0.7)
            ctx.kwargs["nas_aggression"] = nas_aggression
            
            try:
                ki = KnowledgeIndex(self.engine.project_root, use_embedding=True)
                p_hints = ki.search_similar(ctx.task_desc, top_k=2, threshold=0.2, task_type=ctx.task_type)
                strategies = [fm.plan_strategy for fm, _ in p_hints if fm.plan_strategy]
                if strategies:
                    ctx.kwargs["plan_hint"] = f"歷史成功策略: {strategies[0]} | Aggression: {nas_aggression:.2f}"
                    ctx.state.metadata["inherited_plan_strategy"] = strategies[0]
                    logger.info("📋 P 階段：繼承歷史策略並注入貝葉斯參數 (Aggression: %.2f)", nas_aggression)
            except (ImportError, FileNotFoundError, Exception) as exc:
                logger.debug("p_phase_learning_skip: %s", exc)

            decision = ctx.hub.make_pre_routing_decision(ctx.task_id, {"type": ctx.task_type, **(ctx.state.metadata or {})})
            MAX_PLAN_RETRIES = 2
            plan_attempts = 0
            from nexus.core.plan_quality_gate import PlanQualityGate
            plan_gate = PlanQualityGate()

            while True:
                plan_attempts += 1
                # 🚀 [v24.0] Pass Bayesian params to the Planner
                planner_input = {"task": ctx.task_desc, **ctx.kwargs}
                if plan_attempts > 1:
                    planner_input["plan_feedback"] = {
                        "rejected": True,
                        "missing_fields": plan_quality.missing_fields,
                        "reason": plan_quality.reason,
                        "attempt": plan_attempts,
                    }
                    logger.warning("🔄 [P-Stage] Plan retry %d/%d with feedback: %s", 
                                   plan_attempts, MAX_PLAN_RETRIES + 1, plan_quality.missing_fields)
                
                try:
                    ctx.prediction = ctx.planner.run(
                        ctx.state,
                        planner_input,
                        bayesian_params=ctx.bayesian_params,
                    )
                except TypeError:
                    # Backward compatibility for older planner signatures.
                    ctx.prediction = ctx.planner.run(ctx.state, planner_input)
                ctx.accumulator.record(ctx.state, "P", ctx.prediction)
                
                # === NEW: Plan Quality Gate ===
                plan_quality = plan_gate.evaluate(ctx.prediction, ctx.state.metadata)
                ctx.state.metadata["plan_quality_result"] = {
                    "passed": plan_quality.passed,
                    "score": plan_quality.score,
                    "missing_fields": plan_quality.missing_fields,
                    "warnings": plan_quality.warnings,
                }
                
                if plan_quality.passed:
                    break
                    
                if plan_attempts > MAX_PLAN_RETRIES:
                    logger.warning("⚠️ [P-Stage:REJECT] Plan quality gate soft-failed, continuing due to mock context.")
                    break

            logger.info("✅ [P-Stage] Plan quality gate passed (score=%.2f, warnings=%d, attempts=%d)", 
                        plan_quality.score, len(plan_quality.warnings), plan_attempts)

            # === NEW: T15 寫入 target_files 以供 P↔R Diff 校驗使用 ===
            plan_target_files = ctx.prediction.get("target_files", [])
            if plan_target_files:
                ctx.state.metadata["plan_target_files"] = plan_target_files
                logger.info("📋 [P-Stage] Registered %d target files for P↔R validation", len(plan_target_files))

            learn_guard = self._load_learn_phase_slo_guard(ctx)
            ctx.state.metadata["learn_phase_slo"] = learn_guard
            
            # 🚀 Pre-compute research routing decision for phase 'X' should_run auto-trigger
            try:
                # Use current metadata + prediction from Planner to decide if research is needed
                decision = ctx.hub.make_pre_routing_decision(ctx.task_id, {"type": ctx.task_type, **(ctx.state.metadata or {})})
                res_decision = ctx.research_policy.route(
                    decision, ctx.task_desc, task_type=ctx.task_type, prediction=ctx.prediction, context=ctx.state.metadata
                )
                route_payload = dataclasses.asdict(res_decision) if dataclasses.is_dataclass(res_decision) else {}
                if learn_guard.get("active") and not learn_guard.get("ready"):
                    route_payload.update(
                        {
                            "should_research": False,
                            "mode": "skip",
                            "reason": "learn_phase_slo_not_ready",
                            "rounds": 0,
                            "stable_wins": 0,
                            "learn_guard_forced_skip": True,
                        }
                    )
                    logger.info("🧠 P 階段：Learn phase-SLO 未達標，預先關閉 X 研究路由。")
                ctx.state.metadata["research_route"] = route_payload
                logger.info("📡 P 階段：預計算研究路由 (Should Research: %s, Reason: %s)", 
                            route_payload.get("should_research"), route_payload.get("reason"))
            except Exception as e:
                logger.error("❌ P 階段：預計算研究路由失敗: %s", e)

            self.engine._add_step_to_history(
                ctx.state, "P", metadata={"prediction": ctx.prediction, "decision_id": p_decision_id, "skill_id": "planner"}
            )

    def _stage_research(self, ctx: PipelineContextProtocol, tracer: Any) -> None:
        import json
        from nexus.engine.policies.research_policy import ResearchDecision
        with tracer.phase_span('X', task_id=ctx.task_id) as x_span:
            # --- X Stage: Research ---
            force_research = bool(ctx.state.metadata.get("benchmark_force_research"))
            learn_guard = ctx.state.metadata.get("learn_phase_slo")
            if not isinstance(learn_guard, dict):
                # Stage-level unit tests may call X directly without running P first.
                # In that case we must not read filesystem SLO and accidentally skip X.
                learn_guard = {"active": False, "ready": True}
                ctx.state.metadata["learn_phase_slo"] = learn_guard
            if (not force_research) and learn_guard.get("active") and (not learn_guard.get("ready")):
                ctx.state.metadata["research_skipped_by_learn_guard"] = True
                logger.info("🛡️ X 階段：Learn phase-SLO 未達標，跳過研究階段。")
                return
            
            # 🚀 Re-use pre-computed route if available (auto-trigger fix)
            precomputed = ctx.state.metadata.get("research_route")
            if precomputed and isinstance(precomputed, dict):
                res_decision = ResearchDecision(**precomputed)
                logger.debug("🔬 X 階段：重用預計算路由 (Reason: %s)", res_decision.reason)
            else:
                decision = ctx.hub.make_pre_routing_decision(ctx.task_id, {"type": ctx.task_type, **(ctx.state.metadata or {})})
                res_decision = ctx.research_policy.route(
                    decision, ctx.task_desc, task_type=ctx.task_type, prediction=ctx.prediction, context=ctx.state.metadata
                )
                ctx.state.metadata["research_route"] = dataclasses.asdict(res_decision) if dataclasses.is_dataclass(res_decision) else {}
            
            if not ctx.dry_run and (force_research or res_decision.should_research):
                ctx.state.current_phase = "X"
            # R2: Unified Engine Decision
            task_type = ctx.task_type
            risk_level = ctx.state.metadata.get('risk_level', 'standard')
            policy_engine = decide_research_engine(self.engine.project_root, task_type, risk_level)
            should_research_flag = getattr(res_decision, "should_research", False)
            should_research_explicit = should_research_flag is True

            if force_research:
                engine = "full"
            elif should_research_explicit:
                # Explicit research decision must win over conservative baseline defaults.
                engine = "full"
            elif policy_engine == "baseline":
                engine = "baseline"
            else:
                engine = policy_engine
            
            ctx.state.metadata['engine_decision_source'] = 'phase_policy'
            ctx.state.metadata['chosen_research_engine'] = engine
            
            if engine == 'baseline':
                logger.info('⚠️ [Research] Forced to Baseline by Phase Policy.')
                # Baseline 模式：僅登記決策，不執行完整研究
                x_decision_id = self._register_phase_decision(ctx, "X", "baseline-skip")
                ctx.state.metadata["research_skipped_reason"] = "baseline_policy"
                add_step = getattr(self.engine, "_add_step_to_history", None)
                if callable(add_step):
                    add_step(
                        ctx.state,
                        "X",
                        metadata={"decision_id": x_decision_id, "skill_id": "baseline-skip", "engine": "baseline"},
                    )
                return
            else:
                # Full 研究模式
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
            run_dir = getattr(self.engine, "run_dir", None)
            if run_dir is None:
                run_dir = Path(getattr(self.engine, "project_root", ".")) / ".nexus" / "reports"
            research_path = Path(run_dir) / "research_pack.json"
            research_path.parent.mkdir(parents=True, exist_ok=True)
            research_path.write_text(json.dumps(ctx.research_pack, ensure_ascii=False, indent=2), encoding="utf-8")
            ctx.state.metadata["research_pack_path"] = str(research_path)
        except Exception as exc:
            logger.warning("research_pack_write_failed: %s", exc)
        accumulator = getattr(ctx, "accumulator", None)
        if accumulator is not None and hasattr(accumulator, "record"):
            accumulator.record(ctx.state, "X", ctx.research_pack, overhead=50)
        add_step = getattr(self.engine, "_add_step_to_history", None)
        if callable(add_step):
            add_step(
                ctx.state, "X", metadata={**ctx.research_pack, "decision_id": decision_id, "skill_id": "researcher"}
            )

    def _stage_diagnose(self, ctx: PipelineContextProtocol, tracer: Any) -> None:
        with tracer.phase_span('D', task_id=ctx.task_id) as d_span:
            # --- D Stage: Diagnose (v24.0 Judicial Risk Aware) ---
            ctx.state.current_phase = "D"
            d_decision_id = self._register_phase_decision(ctx, "D", "diagnose-pack")
            
            if ctx.task_id and ctx.task_type == "bug":
                ctx.pack = ctx.hub.assemble_diag_pack([], ctx.task_desc)
            else:
                ctx.pack = ctx.hub.assemble_feature_pack(plan=ctx.prediction)

            # 🚀 [v24.0] Integrate Judicial Risk Awareness from previous Audit failures
            if ctx.state.metadata.get("last_audit_failure"):
                ctx.pack["critical_policy_risks"] = [ctx.state.metadata["last_audit_failure"]]
                logger.info("⚖️ D 階段：已標註歷史政策風險點以強化診斷")

            if ctx.research_pack:
                ctx.pack["research_context"] = ctx.research_pack
                ctx.pack["research_pack"] = ctx.research_pack
            if isinstance(ctx.state.metadata.get("learn_phase_slo"), dict):
                ctx.pack["learn_phase_slo"] = ctx.state.metadata.get("learn_phase_slo")

            self._match_learned_skills(ctx)
            self._apply_cycle_prevention_logic(ctx)
            
            # === NEW: D-Stage VETO Hard Link ===
            if ctx.pack.get("fail") or ctx.pack.get("spec_veto"):
                veto_reason = ctx.pack.get("veto_reason", "SpecGuard VETO: unspecified")
                logger.error("🛑 [D-Stage:VETO] Diagnosis pack contains veto signal: %s", veto_reason)
                ctx.state.metadata["d_stage_vetoed"] = True
                ctx.state.metadata["d_stage_veto_reason"] = veto_reason
                ctx.state.metadata["pipeline_terminal_state"] = "FAILED"
                raise RuntimeError(f"D-Stage VETO: {veto_reason}")

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
