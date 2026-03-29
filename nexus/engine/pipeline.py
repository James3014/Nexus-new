import logging
import time
import json
import subprocess
import sys
import dataclasses
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, Optional

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
    planner: Any
    researcher: Any
    repairer: Any
    # Mutable inter-stage data
    decision_counter: int = 0
    prediction: Any = None
    research_pack: Any = None
    pack: dict = field(default_factory=dict)

class NexusPipeline:
    """⚙️ Nexus Task Pipeline (P-X-D-R-A-C)
    
    IDENTITY: Nexus is a Battlesuit (戰甲), NOT an Agent.
    The AI model wearing Nexus executes tasks through this 6-phase pipeline.
    The learning system belongs to Nexus (the armor), not to any specific model.
    Experience persists across model switches — whoever wears the armor benefits.
    """
    def __init__(self, engine):
        self.engine = engine

    def _run_experimental_research(
        self,
        *,
        task_id: str,
        task_desc: str,
        workspace: str,
        rounds: int,
        stable_wins: int,
        proof_ratio_min: float,
    ) -> Dict[str, Any]:
        workspace_path = Path(workspace).expanduser()
        if not workspace_path.is_absolute():
            workspace_path = (self.engine.project_root / workspace_path).resolve()
        else:
            workspace_path = workspace_path.resolve()
        script = self.engine.project_root / "scripts" / "ops" / "phase7_autotune_loop.py"
        prefix = f"xphase_{task_id}"
        start_ts = time.time()
        cmd = [
            sys.executable,
            str(script),
            "--project-root",
            str(self.engine.project_root),
            "--workspace",
            str(workspace_path),
            "--rounds",
            str(rounds),
            "--proof-ratio-min",
            str(proof_ratio_min),
            "--max-loops",
            str(max(stable_wins + 2, 3)),
            "--stable-wins",
            str(stable_wins),
            "--output-prefix",
            prefix,
        ]
        rc = subprocess.call(cmd, cwd=str(self.engine.project_root))
        report_path = workspace_path / f"{prefix}_final_report_cn.json"
        report: Dict[str, Any] = {}
        if report_path.exists():
            try:
                report = json.loads(report_path.read_text(encoding="utf-8"))
            except Exception:
                report = {}

        history = list(report.get("history", []) or [])
        hypotheses: list[dict[str, Any]] = []
        experiments: list[dict[str, Any]] = []
        for idx, row in enumerate(history, start=1):
            best = dict(row.get("best", {}) or {})
            hid = f"H{idx}"
            hypotheses.append(
                {
                    "id": hid,
                    "description": f"min_samples={best.get('min_samples')} baseline={best.get('baseline')} learning_rate={best.get('learning_rate')}",
                    "confidence": 0.8 if int(row.get("apply_rc", 1) or 1) == 0 else 0.4,
                }
            )
            experiments.append(
                {
                    "round": idx,
                    "hypothesis": hid,
                    "metric": 1.0 if int(row.get("apply_rc", 1) or 1) == 0 else 0.0,
                    "kept": int(row.get("apply_rc", 1) or 1) == 0,
                    "sweep_report": row.get("sweep_report"),
                }
            )

        final_best = dict(report.get("final_best", {}) or {})
        winner = {
            "hypothesis_id": f"H{len(history)}" if history else "",
            "patch_diff": "",
            "final_metric": 1.0 if bool(report.get("converged")) else 0.0,
            "params": final_best,
            "report_path": str(report_path),
        }
        eliminated = [h["id"] for h in hypotheses[:-1]] if hypotheses else []
        elapsed = time.time() - start_ts
        return build_research_pack(
            task=task_desc,
            mode="experimental",
            source="AUTORESEARCH_PHASE7_LOOP",
            reason="router_selected_experimental",
            hypotheses=hypotheses,
            experiments=experiments,
            winner=winner,
            eliminated=eliminated,
            rounds=int(report.get("loops_executed", len(history)) or len(history)),
            time_sec=elapsed,
            status="SUCCESS" if bool(report.get("converged")) and rc == 0 else "FAIL",
            findings=[
                f"phase7_loop_rc={rc}",
                f"converged={bool(report.get('converged'))}",
                f"report={report_path}",
            ],
            raw={"report": report, "return_code": rc},
        )

    def run(self, task_desc: str, task_type: str = "bug", context: Optional[Dict] = None, **kwargs) -> bool:
        """EntryPoint for P-X-D-R-A-C pipeline with OTel Tracing wrapper."""
        try:
            from nexus.telemetry.otel_config import init_otel
            init_otel(project_root=self.engine.project_root)
        except Exception:
            logger.debug("otel_init_skipped")  # OTel 初始化失敗不應阻擋

        from nexus.telemetry.tracer import NexusTracer
        tracer = NexusTracer()

        task_id = kwargs.pop("task_id", f"{task_type}-{int(time.time())}")
        
        with tracer.pipeline_span(task_id, **{"nexus.mode": kwargs.get("mode", "developer")}) as (root_span, trace_id, span_id):
            return self._run_pipeline_inner(task_id, trace_id, span_id, task_desc, task_type, context, tracer, **kwargs)

    def _register_phase_decision(self, ctx: PipelineContext, phase: str, skill_id: str) -> str:
        ctx.decision_counter += 1
        decision_id = f"dec_{phase.lower()}_{ctx.task_id}_{ctx.decision_counter}"
        phase_decisions = dict(ctx.state.metadata.get("phase_decisions", {}) or {})
        phase_skills = dict(ctx.state.metadata.get("phase_skills", {}) or {})
        phase_decisions[phase] = decision_id
        phase_skills[phase] = skill_id
        ctx.state.metadata["phase_decisions"] = phase_decisions
        ctx.state.metadata["phase_skills"] = phase_skills
        return decision_id

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
            planner=self.engine.phases.get("P"),
            researcher=self.engine.phases.get("X"),
            repairer=self.engine.phases.get("R"),
        )
        return ctx

    def _stage_plan(self, ctx: PipelineContext, tracer: Any) -> None:
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

    def _stage_research(self, ctx: PipelineContext, tracer: Any) -> None:
        with tracer.phase_span('X', task_id=ctx.task_id) as x_span:
            # --- X Stage: Research ---
            force_research = bool(ctx.state.metadata.get("benchmark_force_research"))
            decision = ctx.hub.make_pre_routing_decision(ctx.task_id, {"type": ctx.task_type, **(ctx.state.metadata or {})})
            research_decision = ctx.research_policy.route(
                decision, ctx.task_desc, task_type=ctx.task_type, prediction=ctx.prediction, context=ctx.state.metadata
            )
            ctx.state.metadata["research_route"] = {
                "should_research": research_decision.should_research,
                "mode": research_decision.mode,
                "reason": research_decision.reason,
                "rounds": research_decision.rounds,
                "stable_wins": research_decision.stable_wins,
            }
            if not ctx.dry_run and (force_research or research_decision.should_research):
                ctx.state.current_phase = "X"
                x_decision_id = self._register_phase_decision(ctx, "X", "researcher")

                try:
                    ki = KnowledgeIndex(self.engine.project_root, use_embedding=True)
                    x_hints = ki.search_similar(ctx.task_desc, top_k=2, threshold=0.3, task_type=ctx.task_type)
                    prior = [fm.winning_hypothesis for fm, _ in x_hints if fm.winning_hypothesis]
                    if prior:
                        ctx.state.metadata["prior_winning_hypotheses"] = prior
                        logger.info("🔬 X 階段：找到 %d 個歷史勝出假設", len(prior))
                except (ImportError, FileNotFoundError, Exception) as exc:
                    logger.debug("x_phase_learning_skip: %s", exc)

                if research_decision.mode == "experimental" and ctx.state.metadata.get("research_workspace"):
                    ctx.research_pack = self._run_experimental_research(
                        task_id=ctx.task_id, task_desc=ctx.task_desc, workspace=str(ctx.state.metadata.get("research_workspace")),
                        rounds=max(int(ctx.state.metadata.get("research_rounds", research_decision.rounds) or 0), 1),
                        stable_wins=max(int(ctx.state.metadata.get("research_stable_wins", research_decision.stable_wins) or 0), 1),
                        proof_ratio_min=float(ctx.state.metadata.get("research_proof_ratio_min", 95.0) or 95.0)
                    )
                else:
                    legacy_pack = ctx.researcher.run(ctx.state, {"task": ctx.task_desc})
                    ctx.research_pack = build_research_pack(
                        task=ctx.task_desc, mode="external", source=str(legacy_pack.get("source", "INTERNAL")),
                        reason=research_decision.reason, hypotheses=[], experiments=[], winner={}, eliminated=[],
                        rounds=research_decision.rounds, time_sec=0.0, status=str(legacy_pack.get("status", "FAIL")),
                        findings=list(legacy_pack.get("findings", []) or []), raw=legacy_pack
                    )
                try:
                    research_path = self.engine.run_dir / "research_pack.json"
                    research_path.write_text(json.dumps(ctx.research_pack, ensure_ascii=False, indent=2), encoding="utf-8")
                    ctx.state.metadata["research_pack_path"] = str(research_path)
                except (OSError, TypeError) as exc:
                    logger.warning("research_pack_write_failed: %s", exc)
                ctx.accumulator.record(ctx.state, "X", ctx.research_pack, overhead=50)
                self.engine._add_step_to_history(
                    ctx.state, "X", metadata={**ctx.research_pack, "decision_id": x_decision_id, "skill_id": "researcher"}
                )

    def _stage_diagnose(self, ctx: PipelineContext, tracer: Any) -> None:
        with tracer.phase_span('D', task_id=ctx.task_id) as d_span:
            # --- D Stage: Diagnose ---
            ctx.state.current_phase = "D"
            d_decision_id = self._register_phase_decision(ctx, "D", "diagnose-pack")
            if ctx.task_type == "bug":
                ctx.pack = ctx.hub.assemble_diag_pack([], ctx.task_desc)
            else:
                ctx.pack = ctx.hub.assemble_feature_pack(plan=ctx.prediction)

            if ctx.research_pack:
                ctx.pack["research_context"] = ctx.research_pack
                ctx.pack["research_pack"] = ctx.research_pack

            try:
                knowledge_index = KnowledgeIndex(self.engine.project_root, use_embedding=True)
                similar_skills = knowledge_index.search_similar(ctx.task_desc, top_k=3, threshold=0.1, task_type=ctx.task_type)
                if similar_skills:
                    ctx.pack["learned_skills"] = [
                        {
                            "name": fm.name, "description": fm.description[:200], "task_type": fm.task_type,
                            "keywords": fm.keywords[:5], "score": round(score, 3), "skill_id": fm.task_id,
                            "plan_strategy": fm.plan_strategy, "winning_hypothesis": fm.winning_hypothesis,
                            "phantom_patterns": fm.phantom_patterns, "cycle_count": fm.cycle_count,
                            "cycle_root_cause": fm.cycle_root_cause, "verification_commands": fm.verification_commands,
                        }
                        for fm, score in similar_skills
                    ]
                    ctx.state.metadata["matched_skills_count"] = len(similar_skills)
                    logger.info("🧠 Found %d similar learned skills", len(similar_skills))

                    if knowledge_index._cache:
                        current_ver = knowledge_index._cache.model_version
                        for skill_dict in ctx.pack["learned_skills"]:
                            if skill_dict.get("embedding_model_version") and skill_dict["embedding_model_version"] != current_ver:
                                skill_dict["_embedding_version_mismatch"] = True
                                skill_dict["score"] = round(skill_dict["score"] * 0.5, 3)
                                logger.warning("⚠️ Embedding version mismatch for skill %s, de-weighted score.", skill_dict["skill_id"])
            except (ImportError, FileNotFoundError, ValueError, Exception) as skill_exc:
                logger.warning("learned_skill_lookup_failed: %s", skill_exc)
            
            self.engine._add_step_to_history(
                ctx.state, "D", metadata={"pack_keys": list(ctx.pack.keys()), "decision_id": d_decision_id, "skill_id": "diagnose-pack"}
            )

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
            except (ValueError, KeyError, TypeError, AttributeError) as exc:
                logger.debug("r_phase_cycle_prevention_skip: %s", exc)

    def _execute_single_repair(self, ctx: PipelineContext, tracer: Any, repair_attempts: int) -> dict:
        # RCA Early Trigger
        if repair_attempts >= 2:
            ctx.pack["force_deep_diagnosis"] = True
            logger.info("🩺 連續失敗 ≥2，強制深度診斷")
            NexusEventBus.publish("repair_failed", {"task_id": ctx.state.task_id, "attempt": repair_attempts})

        # Load full skill context
        try:
            learned = ctx.pack.get("learned_skills", [])
            if learned and learned[0].get("score", 0) >= 0.3:
                best_skill_id = learned[0]["skill_id"]
                knowledge_index = KnowledgeIndex(self.engine.project_root)
                full_skill = knowledge_index.load_full_skill(best_skill_id)
                if full_skill:
                    ctx.pack["skill_context"] = full_skill[:2000]
                    ctx.state.metadata["skill_context_loaded"] = best_skill_id
                    logger.info("📚 Loaded skill context: %s", best_skill_id)
        except (ImportError, FileNotFoundError, ValueError, Exception) as skill_ctx_exc:
            logger.warning("skill_context_load_fallback: %s", skill_ctx_exc)

        with tracer.phase_span('R', task_id=ctx.task_id) as r_span:
            res = ctx.repairer.run(ctx.state, ctx.pack)
            ctx.accumulator.record(ctx.state, "R", res, overhead=100)
            
        current_time = float(time.time() - float(ctx.state.metadata.get("start_time", time.time())))
        current_decision_id = str((ctx.state.metadata.get("phase_decisions", {}) or {}).get("R") or self._register_phase_decision(ctx, "R", "default-repair"))
        current_skill_id = str((ctx.state.metadata.get("phase_skills", {}) or {}).get("R") or "default-repair")
        
        review_status_raw = "REJECTED"
        result_object = {}
        if isinstance(res, dict):
            review_status_raw = res.get("status", "REJECTED")
            ctx.state.metadata["last_review_status"] = review_status_raw
            result_object = res.get("result_object", {})
            ctx.state.metadata["last_patch_generated"] = bool(result_object.get("patch_generated", False))
            ctx.state.metadata["last_patch_apply_success"] = bool(result_object.get("patch_apply_success", False))
            ctx.state.metadata["last_no_change_reason"] = str(result_object.get("no_change_reason", "") or "")
            ctx.state.metadata["last_proof_type"] = str(result_object.get("proof_type", "") or "")
            ctx.state.metadata["last_proof_value"] = str(result_object.get("proof_value", "") or "")
            ctx.state.metadata["sandbox_mode"] = result_object.get("sandbox_mode", "unknown")

            audit_meta = result_object.get("audit_metadata", {})
            if audit_meta.get("verify_commands"):
                ctx.state.metadata["verification_commands"] = audit_meta["verify_commands"]
            if audit_meta.get("return_codes"):
                ctx.state.metadata["verification_exit_codes"] = list(audit_meta["return_codes"].values())
        elif isinstance(res, list):
            latest_res = res[-1] if res else {}
            for key in ["scope_drift", "insufficient_diag"]:
                if isinstance(latest_res, dict) and key in latest_res:
                    ctx.pack[key] = latest_res[key]
                    if "signals" not in ctx.state.metadata:
                        ctx.state.metadata["signals"] = {}
                    ctx.state.metadata["signals"][key] = latest_res[key]

        # Pregate
        pregate_passed = True
        try:
            from nexus.engine.cli_pregate import run_cli_pregate, _auto_detect_verify_commands

            verify_cmds = list(ctx.state.metadata.get("verification_commands", []))
            pack_verify = ctx.pack.get("verify_commands", [])
            if pack_verify:
                verify_cmds.extend(pack_verify)

            if not verify_cmds:
                verify_cmds = _auto_detect_verify_commands(self.engine.project_root)

            if not verify_cmds:
                ctx.state.metadata["pregate_skip"] = True
                ctx.state.metadata["pregate_skip_reason"] = "no_verify_commands_detected"
                logger.info("⚠️ CLI Pre-Gate SKIPPED: no verify commands detected")
            elif str(review_status_raw) != "REJECTED":
                logger.info("🚦 CLI Pre-Gate Triggered: Running %d verify commands", len(verify_cmds))
                pregate_passed, pregate_results = run_cli_pregate(
                    self.engine.project_root, verify_cmds, timeout_per_cmd=60
                )
                ctx.state.metadata["cli_pregate_results"] = pregate_results
                ctx.state.metadata["pregate_skip"] = False
                ctx.state.metadata["verification_commands"] = verify_cmds
                ctx.state.metadata["verification_exit_codes"] = [r["exit_code"] for r in pregate_results]

                if not pregate_passed:
                    review_status_raw = "REJECTED"
                    result_object["cli_pregate_rejected"] = True
                    logger.info("🚫 CLI Pre-Gate 攔截：強制退回修復重試")
        except (subprocess.TimeoutExpired, OSError, ValueError) as exc:
            logger.debug("cli_pregate_skip: %s", exc)

        self.engine._add_step_to_history(
            ctx.state,
            "R",
            metadata={
                "status": "executed",
                "decision_id": current_decision_id,
                "skill_id": current_skill_id,
                "attempt": repair_attempts,
            },
        )
        return {"status": review_status_raw, "result": result_object, "current_decision_id": current_decision_id, "current_skill_id": current_skill_id}

    def _evaluate_audit_result(self, ctx: PipelineContext, tracer: Any, repair_attempts: int, review_status_raw: str, result_object: dict, current_decision_id: str, current_skill_id: str) -> dict:
        ctx.state.current_phase = "A"
        a_decision_id = self._register_phase_decision(ctx, "A", "audit-review")
        ctx.state.metadata["last_audit_decision_id"] = a_decision_id
        ctx.state.metadata["last_repair_decision_id"] = current_decision_id
        self.engine._add_step_to_history(
            ctx.state,
            "A",
            metadata={"status": review_status_raw, "decision_id": a_decision_id, "skill_id": "audit-review"},
        )

        try:
            from nexus.learning.knowledge_index import KnowledgeIndex
            ki = KnowledgeIndex(self.engine.project_root, use_embedding=True)
            a_hints = ki.search_similar(ctx.task_desc, top_k=3, threshold=0.2, task_type=ctx.task_type)
            known_phantoms = []
            for fm, _ in a_hints:
                known_phantoms.extend(fm.phantom_patterns)
            if known_phantoms:
                ctx.state.metadata["known_phantom_patterns"] = known_phantoms
                if "missing_physical_proof" in known_phantoms:
                    ctx.state.metadata["require_strict_proof"] = True
                logger.info("🛡️ A 階段：預載 %d 個歷史幻覺模式", len(known_phantoms))
        except (ImportError, FileNotFoundError, ValueError, Exception) as exc:
            logger.debug("a_phase_learning_skip: %s", exc)

        with tracer.phase_span('A', task_id=ctx.task_id) as a_span:
            status, audit_success = self.engine.ReviewStatusNormalizer.normalize(review_status_raw)
            checks = int(ctx.state.metadata.get("anti_hallucination_checks", 0) or 0) + 1
            ctx.state.metadata["anti_hallucination_checks"] = checks
            phantom_reason = detect_inconclusive_success(
                status=review_status_raw,
                patch_generated=result_object.get("patch_generated", False),
                patch_apply_success=result_object.get("patch_apply_success", False),
                no_change_reason=result_object.get("no_change_reason", ""),
                proof_type=result_object.get("proof_type", ""),
                proof_value=result_object.get("proof_value", ""),
            )
        if phantom_reason:
            audit_success = False
            status = "REJECTED"
            ctx.state.metadata["phantom_success_reason"] = phantom_reason
            ctx.state.metadata["anti_hallucination_block_count"] = int(
                ctx.state.metadata.get("anti_hallucination_block_count", 0) or 0
            ) + 1
            NexusEventBus.publish("phantom_detected", {"task_id": ctx.state.task_id, "reason": phantom_reason})
        elif audit_success:
            ctx.state.metadata["anti_hallucination_pass_count"] = int(
                ctx.state.metadata.get("anti_hallucination_pass_count", 0) or 0
            ) + 1

        proof_present = bool(
            str(result_object.get("proof_type", "") or "")
            and str(result_object.get("proof_value", "") or "")
        )
        try:
            event = build_outcome_event(
                task_id=ctx.state.task_id,
                phase="R",
                decision_id=current_decision_id,
                skill_id=current_skill_id,
                passed=bool(audit_success),
                phantom_blocked=bool(phantom_reason),
                repair_success=bool(audit_success),
                retry_count=max(0, repair_attempts - 1),
                proof_present=proof_present,
                regression_pass_rate=100.0 if audit_success else 0.0,
                pattern_reuse=float(ctx.state.metadata.get("pattern_reuse_rate", 0.0) or 0.0),
                next_run_hit=float(ctx.state.metadata.get("next_run_hit_rate", 0.0) or 0.0),
                metadata={
                    "status": status,
                    "audit_status": review_status_raw,
                    "source": "pipeline.repair_audit",
                },
            )
            append_skill_outcome_event(self.engine.project_root, event)
        except (OSError, RuntimeError, ValueError) as exc:
            logger.warning("skill_outcome_event_write_failed: %s", exc)

        return {"audit_success": audit_success, "status": status, "phantom_reason": phantom_reason}

    def _handle_escalation(self, ctx: PipelineContext, repair_attempts: int, review_status_raw: str, phantom_reason: str) -> bool:
        rejection_history = list(ctx.state.metadata.get("rejection_history", []))
        reason_tag = phantom_reason if phantom_reason else f"rejected:{review_status_raw}"
        rejection_history.append(reason_tag)
        ctx.state.metadata["rejection_history"] = rejection_history

        ctx.state.metadata["last_audit_failure"] = (
            f"phantom success: {phantom_reason}" if phantom_reason else f"rejected: {review_status_raw}"
        )
        ctx.pack["audit_feedback"] = ctx.state.metadata["last_audit_failure"]

        if repair_attempts >= 3:
            try:
                from nexus.learning.cycle_analyzer import analyze_cycle
                mid_cycle = analyze_cycle(rejection_history)
                mid_root = mid_cycle.get("root_cause", "")
                if mid_root in ("scope_drift", "insufficient_diag"):
                    esc_count = int(ctx.state.metadata.get("escalation_count", 0)) + 1
                    ctx.state.metadata["escalation_count"] = esc_count

                    if esc_count > 2:
                        logger.error("🛑 Max escalation reached (%d). Entering HUMAN_REVIEW.", esc_count)
                        ctx.state.metadata["human_review_required"] = True
                        ctx.state.metadata["human_review_reason"] = f"max_escalation:{mid_root}"
                        NexusEventBus.publish("human_review_required", {
                            "task_id": ctx.state.task_id,
                            "root_cause": mid_root,
                            "escalation_count": esc_count,
                        })
                        return True

                    logger.warning("📢 Escalation: R↔A loop root_cause=%s, jumping back to P", mid_root)
                    ctx.state.metadata["escalation_triggered"] = True
                    ctx.state.metadata["escalation_root_cause"] = mid_root
                    NexusEventBus.publish("escalation_to_plan", {
                        "task_id": ctx.state.task_id,
                        "root_cause": mid_root,
                        "attempt": repair_attempts,
                    })
                    return True
            except (ValueError, TypeError, KeyError) as esc_exc:
                logger.debug("escalation_analysis_failed: %s", esc_exc)
        return False

    def _repair_audit_loop(self, ctx: PipelineContext, tracer: Any) -> bool:
        # --- R/A Stage: Repair Loop ---
        repair_attempts = 0
        success = False
        if ctx.dry_run:
            repair_attempts = 1
            ctx.state.retry_count = 0
            ctx.state.current_phase = "R"
            current_decision_id = self._register_phase_decision(ctx, "R", "dry-run-repair")
            current_skill_id = "dry-run-repair"
            review_status_raw = "APPROVED"
            status = "APPROVED"
            audit_success = True
            ctx.state.metadata["last_review_status"] = review_status_raw
            ctx.state.metadata["last_patch_generated"] = False
            ctx.state.metadata["last_patch_apply_success"] = True
            ctx.state.metadata["last_no_change_reason"] = "dry_run_mode"
            ctx.state.metadata["last_proof_type"] = ""
            ctx.state.metadata["last_proof_value"] = ""
            self.engine._add_step_to_history(
                ctx.state,
                "R",
                metadata={
                    "status": "executed",
                    "decision_id": current_decision_id,
                    "skill_id": current_skill_id,
                    "attempt": repair_attempts,
                    "dry_run_mode": True,
                },
            )
            ctx.state.current_phase = "A"
            a_decision_id = self._register_phase_decision(ctx, "A", "audit-review")
            ctx.state.metadata["last_audit_decision_id"] = a_decision_id
            ctx.state.metadata["last_repair_decision_id"] = current_decision_id
            self.engine._add_step_to_history(
                ctx.state,
                "A",
                metadata={
                    "status": review_status_raw,
                    "decision_id": a_decision_id,
                    "skill_id": "audit-review",
                    "dry_run_mode": True,
                },
            )
            try:
                event = build_outcome_event(
                    task_id=ctx.state.task_id,
                    phase="R",
                    decision_id=current_decision_id,
                    skill_id=current_skill_id,
                    passed=True,
                    phantom_blocked=False,
                    repair_success=True,
                    retry_count=0,
                    proof_present=False,
                    regression_pass_rate=100.0,
                    pattern_reuse=float(ctx.state.metadata.get("pattern_reuse_rate", 0.0) or 0.0),
                    next_run_hit=float(ctx.state.metadata.get("next_run_hit_rate", 0.0) or 0.0),
                    metadata={
                        "status": status,
                        "audit_status": review_status_raw,
                        "source": "pipeline.dry_run",
                    },
                )
                append_skill_outcome_event(self.engine.project_root, event)
            except (OSError, RuntimeError, ValueError) as exc:
                logger.warning("skill_outcome_event_write_failed: %s", exc)
            success = True

        while (not ctx.dry_run) and repair_attempts < self.engine.max_retries:
            from nexus.core.event_bus import NexusEventBus
            external_signals = NexusEventBus.drain_signals("force_replan")
            if external_signals:
                logger.warning("📡 External signal received: force_replan. Breaking R↔A loop.")
                ctx.state.metadata["external_force_replan"] = True
                break

            repair_attempts += 1
            ctx.state.retry_count = max(ctx.state.retry_count, repair_attempts - 1)
            ctx.state.current_phase = "R"
            logger.info(f"🛠️ [Pipeline] Attempt {repair_attempts}/{self.engine.max_retries}")

            r_out = self._execute_single_repair(ctx, tracer, repair_attempts)
            review_status_raw = r_out["status"]
            result_object = r_out["result"]
            current_decision_id = r_out["current_decision_id"]
            current_skill_id = r_out["current_skill_id"]

            a_out = self._evaluate_audit_result(ctx, tracer, repair_attempts, review_status_raw, result_object, current_decision_id, current_skill_id)
            audit_success = a_out["audit_success"]
            status = a_out["status"]
            phantom_reason = a_out["phantom_reason"]

            if audit_success:
                success = True
                break

            if status == "REJECTED" and repair_attempts < self.engine.max_retries:
                if self._handle_escalation(ctx, repair_attempts, review_status_raw, phantom_reason):
                    break
                logger.warning(f"🔄 Audit Rejected. Retrying repair (Status: {status})")
                continue
            else:
                break
                
        return success

    def _stage_crystallize(self, ctx: PipelineContext, success: bool, tracer: Any) -> None:
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
        
        from nexus.engine.pipeline_outcome import PipelineOutcome, PipelineTerminalState, HumanReviewHandoff
        
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
            from nexus.learning.cycle_analyzer import analyze_cycle
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
        
        from nexus.core.outcome_schema import NexusOutcomeV2
        from datetime import datetime, timezone
        import os
        
        commit_sha = "unknown"
        try:
            commit_sha = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=str(self.engine.project_root), stderr=subprocess.DEVNULL
            ).decode().strip()
        except (subprocess.CalledProcessError, OSError, FileNotFoundError):
            pass
            
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

        if success:
            ctx.state.current_phase = "C"
            c_decision_id = self._register_phase_decision(ctx, "C", "crystallize")
            self.engine._add_step_to_history(
                ctx.state, "C", metadata={"decision_id": c_decision_id, "skill_id": "crystallize"}
            )
            try:
                c_event = build_outcome_event(
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
                append_skill_outcome_event(self.engine.project_root, c_event)

                try:
                    outcome_dict = c_event.to_dict() if hasattr(c_event, "to_dict") else vars(c_event)
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
                                    NexusEventBus.publish("skill_shared", {
                                        "task_id": ctx.state.task_id,
                                        "registry_path": str(exchange.registry.db_path),
                                    })
                        except (OSError, ConnectionError, RuntimeError, ValueError) as share_exc:
                            logger.warning("skill_push_failed: %s", share_exc)
                except (ValueError, TypeError, OSError) as artifact_exc:
                    logger.warning("skill_artifact_generation_failed: %s", artifact_exc)

            except (OSError, RuntimeError, ValueError) as exc:
                logger.warning("skill_outcome_event_write_failed: %s", exc)
            self.engine.state_io.save_global_state(ctx.state)
            self.engine.commander.next_step(status="completed", state=ctx.state)
        else:
            try:
                fail_decision_id = self._register_phase_decision(ctx, "C", "crystallize")
                fail_event = build_outcome_event(
                    task_id=ctx.state.task_id,
                    phase="C",
                    decision_id=fail_decision_id,
                    skill_id="crystallize",
                    passed=False,
                    phantom_blocked=bool(ctx.state.metadata.get("phantom_success_reason")),
                    repair_success=False,
                    retry_count=max(0, ctx.state.retry_count),
                    proof_present=bool(
                        str(ctx.state.metadata.get("last_proof_type", "") or "")
                        and str(ctx.state.metadata.get("last_proof_value", "") or "")
                    ),
                    regression_pass_rate=0.0,
                    pattern_reuse=float(ctx.state.metadata.get("pattern_reuse_rate", 0.0) or 0.0),
                    next_run_hit=float(ctx.state.metadata.get("next_run_hit_rate", 0.0) or 0.0),
                    metadata={"status": "FAILED", "audit_status": "REJECTED", "source": "pipeline.crystallize"},
                )
                append_skill_outcome_event(self.engine.project_root, fail_event)
            except (OSError, RuntimeError, ValueError) as exc:
                logger.warning("skill_outcome_event_write_failed: %s", exc)

    def _finalize_and_report(self, ctx: PipelineContext, success: bool, tracer: Any) -> bool:
        health_score = ctx.health_evaluator.evaluate(ctx.state, success)
        logger.info(f"📊 Final Health: {health_score:.1f}% | Success: {success}")

        self.engine.state_io.save_global_state(ctx.state)
        if ctx.state.metadata.get("pipeline_terminal_state") == "HUMAN_REVIEW":
            logger.error("🛑 Pipeline 終止於 HUMAN_REVIEW，需人工介入")
            from nexus.core.handoff_bundle import HandoffBundleWriter
            writer = HandoffBundleWriter(self.engine.project_root)
            writer.create(
                triggering_phase="pipeline_terminal",
                reason=ctx.state.metadata.get("human_review_reason", "HUMAN_REVIEW triggered"),
                task_id=ctx.state.task_id,
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
        """執行核心 P-X-D-R-A-C 管線"""
        ctx = self._init_pipeline_state(task_id, trace_id, span_id, task_desc, task_type, context, **kwargs)
        self._stage_plan(ctx, tracer)
        self._stage_research(ctx, tracer)
        self._stage_diagnose(ctx, tracer)
        success = self._repair_audit_loop(ctx, tracer)
        self._stage_crystallize(ctx, success, tracer)
        return self._finalize_and_report(ctx, success, tracer)

