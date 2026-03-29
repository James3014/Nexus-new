import logging
import time
import json
import subprocess
import sys
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
            pass  # OTel 初始化失敗不應阻擋

        from nexus.telemetry.tracer import NexusTracer
        tracer = NexusTracer()

        task_id = kwargs.pop("task_id", f"{task_type}-{int(time.time())}")
        
        with tracer.pipeline_span(task_id, **{"nexus.mode": kwargs.get("mode", "developer")}) as (root_span, trace_id, span_id):
            return self._run_pipeline_inner(task_id, trace_id, span_id, task_desc, task_type, context, tracer, **kwargs)

    def _run_pipeline_inner(self, task_id: str, trace_id: str, span_id: str, task_desc: str, task_type: str = "bug", context: Optional[Dict] = None, tracer: Any = None, **kwargs) -> bool:
        """執行核心 P-X-D-R-A-C 管線"""
        from nexus.core.event_bus import NexusEventBus
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

        decision_counter = 0

        def register_phase_decision(phase: str, skill_id: str) -> str:
            nonlocal decision_counter
            decision_counter += 1
            decision_id = f"dec_{phase.lower()}_{task_id}_{decision_counter}"
            phase_decisions = dict(state.metadata.get("phase_decisions", {}) or {})
            phase_skills = dict(state.metadata.get("phase_skills", {}) or {})
            phase_decisions[phase] = decision_id
            phase_skills[phase] = skill_id
            state.metadata["phase_decisions"] = phase_decisions
            state.metadata["phase_skills"] = phase_skills
            return decision_id
        
        # 🧠 v9.4: Brain-Sync protocol. Load policies from memory service.
        self.engine.policy_manager.apply_policy_to_state(state, task_desc)
        state.metadata["task_description"] = task_desc
        self.engine.state_io.save_global_state(state) # 🛡️ Save before commander loads it
        self.engine.commander.next_step(status="started") # 🎯 Trinity Trigger
        
        # Shortcuts to engine components
        hub = self.engine.hub
        accumulator = self.engine.accumulator
        health_evaluator = self.engine.health_evaluator
        research_policy = self.engine.research_policy
        
        planner = self.engine.phases.get("P")
        researcher = self.engine.phases.get("X")
        repairer = self.engine.phases.get("R")

        with tracer.phase_span('P', task_id=task_id) as p_span:
            # --- P Stage: Plan ---
            state.current_phase = "P"
            p_decision_id = register_phase_decision("P", "planner")

            # 🆕 P 階段學習：查找歷史上同類任務的成功策略
            try:
                from nexus.learning.knowledge_index import KnowledgeIndex
                ki = KnowledgeIndex(self.engine.project_root, use_embedding=True)
                p_hints = ki.search_similar(task_desc, top_k=2, threshold=0.2, task_type=task_type)
                strategies = [fm.plan_strategy for fm, _ in p_hints if fm.plan_strategy]
                if strategies:
                    kwargs["plan_hint"] = f"歷史成功策略: {strategies[0]}"
                    state.metadata["inherited_plan_strategy"] = strategies[0]
                    logger.info("📋 P 階段：繼承歷史策略 → %s", strategies[0])
            except Exception as exc:
                logger.debug("p_phase_learning_skip: %s", exc)

            decision = hub.make_pre_routing_decision(task_id, {"type": task_type, **(context or {})})
            prediction = planner.run(state, {"task": task_desc, **kwargs})
            accumulator.record(state, "P", prediction) # P phase recording
            self.engine._add_step_to_history(
                state,
                "P",
                metadata={"prediction": prediction, "decision_id": p_decision_id, "skill_id": "planner"},
            )

            with tracer.phase_span('X', task_id=task_id) as x_span:
                # --- X Stage: Research ---
                research_pack = None
                force_research = bool(state.metadata.get("benchmark_force_research"))
                research_decision = research_policy.route(
                    decision,
                    task_desc,
                    task_type=task_type,
                    prediction=prediction,
                    context=state.metadata,
                )
                state.metadata["research_route"] = {
                    "should_research": research_decision.should_research,
                    "mode": research_decision.mode,
                    "reason": research_decision.reason,
                    "rounds": research_decision.rounds,
                    "stable_wins": research_decision.stable_wins,
                }
                if not dry_run_mode and (force_research or research_decision.should_research):
                    state.current_phase = "X"
                    x_decision_id = register_phase_decision("X", "researcher")

                    # 🆕 X 階段學習：注入歷史勝出假設
                    try:
                        from nexus.learning.knowledge_index import KnowledgeIndex
                        ki = KnowledgeIndex(self.engine.project_root, use_embedding=True)
                        x_hints = ki.search_similar(task_desc, top_k=2, threshold=0.3, task_type=task_type)
                        prior = [fm.winning_hypothesis for fm, _ in x_hints if fm.winning_hypothesis]
                        if prior:
                            state.metadata["prior_winning_hypotheses"] = prior
                            logger.info("🔬 X 階段：找到 %d 個歷史勝出假設", len(prior))
                    except Exception as exc:
                        logger.debug("x_phase_learning_skip: %s", exc)

                    if research_decision.mode == "experimental" and state.metadata.get("research_workspace"):
                        research_pack = self._run_experimental_research(
                            task_id=task_id,
                            task_desc=task_desc,
                            workspace=str(state.metadata.get("research_workspace")),
                            rounds=max(int(state.metadata.get("research_rounds", research_decision.rounds) or 0), 1),
                            stable_wins=max(int(state.metadata.get("research_stable_wins", research_decision.stable_wins) or 0), 1),
                            proof_ratio_min=float(state.metadata.get("research_proof_ratio_min", 95.0) or 95.0),
                        )
                    else:
                        legacy_pack = researcher.run(state, {"task": task_desc})
                        research_pack = build_research_pack(
                            task=task_desc,
                            mode="external",
                            source=str(legacy_pack.get("source", "INTERNAL")),
                            reason=research_decision.reason,
                            hypotheses=[],
                            experiments=[],
                            winner={},
                            eliminated=[],
                            rounds=research_decision.rounds,
                            time_sec=0.0,
                            status=str(legacy_pack.get("status", "FAIL")),
                            findings=list(legacy_pack.get("findings", []) or []),
                            raw=legacy_pack,
                        )
                    try:
                        research_path = self.engine.run_dir / "research_pack.json"
                        research_path.write_text(json.dumps(research_pack, ensure_ascii=False, indent=2), encoding="utf-8")
                        state.metadata["research_pack_path"] = str(research_path)
                    except Exception as exc:
                        logger.warning("research_pack_write_failed: %s", exc)
                    accumulator.record(state, "X", research_pack, overhead=50)
                    self.engine._add_step_to_history(
                        state,
                        "X",
                        metadata={**research_pack, "decision_id": x_decision_id, "skill_id": "researcher"},
                    )

                with tracer.phase_span('D', task_id=task_id) as d_span:
                    # --- D Stage: Diagnose ---
                    state.current_phase = "D"
                    d_decision_id = register_phase_decision("D", "diagnose-pack")
                    if task_type == "bug":
                        pack = hub.assemble_diag_pack([], task_desc)
                    else:
                        pack = hub.assemble_feature_pack(plan=prediction)

                    if research_pack:
                        pack["research_context"] = research_pack
                        pack["research_pack"] = research_pack

                    # --- Hermes Phase 2: Inject learned skills summary ---
                    try:
                        knowledge_index = KnowledgeIndex(self.engine.project_root, use_embedding=True)
                        similar_skills = knowledge_index.search_similar(task_desc, top_k=3, threshold=0.1, task_type=task_type)
                        if similar_skills:
                            pack["learned_skills"] = [
                                {
                                    "name": fm.name,
                                    "description": fm.description[:200],
                                    "task_type": fm.task_type,
                                    "keywords": fm.keywords[:5],
                                    "score": round(score, 3),
                                    "skill_id": fm.task_id,
                                    "plan_strategy": fm.plan_strategy,
                                    "winning_hypothesis": fm.winning_hypothesis,
                                    "phantom_patterns": fm.phantom_patterns,
                                    "cycle_count": fm.cycle_count,
                                    "cycle_root_cause": fm.cycle_root_cause,
                                    "verification_commands": fm.verification_commands,
                                }
                                for fm, score in similar_skills
                            ]
                            state.metadata["matched_skills_count"] = len(similar_skills)
                            logger.info("🧠 Found %d similar learned skills", len(similar_skills))

                            # 🆕 Embedding 版本校驗
                            if knowledge_index._cache:
                                current_ver = knowledge_index._cache.model_version
                                for skill_dict in pack["learned_skills"]:
                                    if skill_dict.get("embedding_model_version") and skill_dict["embedding_model_version"] != current_ver:
                                        skill_dict["_embedding_version_mismatch"] = True
                                        skill_dict["score"] = round(skill_dict["score"] * 0.5, 3)  # 降權而非丟棄
                                        logger.warning("⚠️ Embedding version mismatch for skill %s, de-weighted score.", skill_dict["skill_id"])
                    except Exception as skill_exc:
                        logger.warning("learned_skill_lookup_failed: %s", skill_exc)
                    self.engine._add_step_to_history(
                        state,
                        "D",
                        metadata={"pack_keys": list(pack.keys()), "decision_id": d_decision_id, "skill_id": "diagnose-pack"},
                    )

                    # 🆕 R 階段循環預防：基於歷史循環根因調整修復策略
                    try:
                        learned = pack.get("learned_skills", [])
                        if learned:
                            best = learned[0]
                            if best.get("cycle_root_cause") == "phantom_proof":
                                pack["enforce_physical_proof"] = True
                                logger.info("🔄 歷史循環根因=phantom_proof，強制要求物理證明")
                            elif best.get("cycle_root_cause") == "insufficient_diag":
                                pack["force_deep_diagnosis"] = True
                                logger.info("🔄 歷史循環根因=insufficient_diag，強制深度診斷")
                    except Exception as exc:
                        logger.debug("r_phase_cycle_prevention_skip: %s", exc)

                    # --- R/A Stage: Repair Loop ---
                    repair_attempts = 0
                    success = False
                    if dry_run_mode:
                        repair_attempts = 1
                        state.retry_count = 0
                        state.current_phase = "R"
                        current_decision_id = register_phase_decision("R", "dry-run-repair")
                        current_skill_id = "dry-run-repair"
                        review_status_raw = "APPROVED"
                        status = "APPROVED"
                        audit_success = True
                        result_object = {
                            "patch_generated": False,
                            "patch_apply_success": True,
                            "no_change_reason": "dry_run_mode",
                            "proof_type": "",
                            "proof_value": "",
                        }
                        state.metadata["last_review_status"] = review_status_raw
                        state.metadata["last_patch_generated"] = False
                        state.metadata["last_patch_apply_success"] = True
                        state.metadata["last_no_change_reason"] = "dry_run_mode"
                        state.metadata["last_proof_type"] = ""
                        state.metadata["last_proof_value"] = ""
                        self.engine._add_step_to_history(
                            state,
                            "R",
                            metadata={
                                "status": "executed",
                                "decision_id": current_decision_id,
                                "skill_id": current_skill_id,
                                "attempt": repair_attempts,
                                "dry_run_mode": True,
                            },
                        )
                        state.current_phase = "A"
                        a_decision_id = register_phase_decision("A", "audit-review")
                        state.metadata["last_audit_decision_id"] = a_decision_id
                        state.metadata["last_repair_decision_id"] = current_decision_id
                        self.engine._add_step_to_history(
                            state,
                            "A",
                            metadata={
                                "status": review_status_raw,
                                "decision_id": a_decision_id,
                                "skill_id": "audit-review",
                                "dry_run_mode": True,
                            },
                        )
                        proof_present = False
                        try:
                            event = build_outcome_event(
                                task_id=state.task_id,
                                phase="R",
                                decision_id=current_decision_id,
                                skill_id=current_skill_id,
                                passed=True,
                                phantom_blocked=False,
                                repair_success=True,
                                retry_count=0,
                                proof_present=proof_present,
                                regression_pass_rate=100.0,
                                pattern_reuse=float(state.metadata.get("pattern_reuse_rate", 0.0) or 0.0),
                                next_run_hit=float(state.metadata.get("next_run_hit_rate", 0.0) or 0.0),
                                metadata={
                                    "status": status,
                                    "audit_status": review_status_raw,
                                    "source": "pipeline.dry_run",
                                },
                            )
                            append_skill_outcome_event(self.engine.project_root, event)
                        except Exception as exc:
                            logger.warning("skill_outcome_event_write_failed: %s", exc)
                        success = True
                    while (not dry_run_mode) and repair_attempts < self.engine.max_retries:
                        # 🆕 外部信號輪詢（每個 R 階段開頭）
                        from nexus.core.event_bus import NexusEventBus
                        external_signals = NexusEventBus.drain_signals("force_replan")
                        if external_signals:
                            logger.warning("📡 External signal received: force_replan. Breaking R↔A loop.")
                            state.metadata["external_force_replan"] = True
                            break

                        repair_attempts += 1
                        state.retry_count = max(state.retry_count, repair_attempts - 1)
                        state.current_phase = "R"
                        logger.info(f"🛠️ [Pipeline] Attempt {repair_attempts}/{self.engine.max_retries}")

                        # RCA Early Trigger
                        if repair_attempts >= 2:
                            pack["force_deep_diagnosis"] = True
                            logger.info("🩺 連續失敗 ≥2，強制深度診斷")
                            NexusEventBus.publish("repair_failed", {"task_id": state.task_id, "attempt": repair_attempts})

                        # R: Repair
                        # --- Hermes Phase 2: Load full skill context for repair ---
                        try:
                            learned = pack.get("learned_skills", [])
                            if learned and learned[0].get("score", 0) >= 0.3:
                                best_skill_id = learned[0]["skill_id"]
                                knowledge_index = KnowledgeIndex(self.engine.project_root)
                                full_skill = knowledge_index.load_full_skill(best_skill_id)
                                if full_skill:
                                    pack["skill_context"] = full_skill[:2000]
                                    state.metadata["skill_context_loaded"] = best_skill_id
                                    logger.info("📚 Loaded skill context: %s", best_skill_id)
                        except Exception as skill_ctx_exc:
                            logger.warning("skill_context_load_failed: %s", skill_ctx_exc)

                        with tracer.phase_span('R', task_id=task_id) as r_span:
                            res = repairer.run(state, pack)
                            accumulator.record(state, "R", res, overhead=100)
                        current_time = float(time.time() - float(state.metadata.get("start_time", time.time())))
                        current_decision_id = str((state.metadata.get("phase_decisions", {}) or {}).get("R") or register_phase_decision("R", "default-repair"))
                        current_skill_id = str((state.metadata.get("phase_skills", {}) or {}).get("R") or "default-repair")

                        # Robust extraction of status
                        review_status_raw = "REJECTED"
                        if isinstance(res, dict):
                            review_status_raw = res.get("status", "REJECTED")
                            state.metadata["last_review_status"] = review_status_raw
                            result_object = res.get("result_object", {})
                            state.metadata["last_patch_generated"] = bool(result_object.get("patch_generated", False))
                            state.metadata["last_patch_apply_success"] = bool(result_object.get("patch_apply_success", False))
                            state.metadata["last_no_change_reason"] = str(result_object.get("no_change_reason", "") or "")
                            state.metadata["last_proof_type"] = str(result_object.get("proof_type", "") or "")
                            state.metadata["last_proof_value"] = str(result_object.get("proof_value", "") or "")
                            # 🆕 記錄沙盒模式
                            state.metadata["sandbox_mode"] = result_object.get("sandbox_mode", "unknown")

                            # 🆕 VDD：捕獲驗證指令
                            audit_meta = result_object.get("audit_metadata", {})
                            if audit_meta.get("verify_commands"):
                                state.metadata["verification_commands"] = audit_meta["verify_commands"]
                            if audit_meta.get("return_codes"):
                                state.metadata["verification_exit_codes"] = list(audit_meta["return_codes"].values())
                        elif isinstance(res, list):
                            latest_res = res[-1] if res else {}
                            for key in ["scope_drift", "insufficient_diag"]:
                                if isinstance(latest_res, dict) and key in latest_res:
                                    pack[key] = latest_res[key]
                                    # Assuming v_span is available in scope or needs to be handled
                                    if "signals" not in state.metadata:
                                        state.metadata["signals"] = {}
                                    state.metadata["signals"][key] = latest_res[key]
                            result_object = {}
                        else:
                            result_object = {}

                        # 🆕 CLI Pre-Gate：R 結束後，先用 exit code 做機械驗證
                        pregate_passed = True
                        try:
                            from nexus.engine.cli_pregate import run_cli_pregate, _auto_detect_verify_commands

                            # 1. 從歷史技能繼承的驗證指令
                            verify_cmds = list(state.metadata.get("verification_commands", []))

                            # 2. 從 diag_pack 傳入的驗證指令
                            pack_verify = pack.get("verify_commands", [])
                            if pack_verify:
                                verify_cmds.extend(pack_verify)

                            # 3. 自動推斷（Python / Rust / Go 等）
                            if not verify_cmds:
                                verify_cmds = _auto_detect_verify_commands(self.engine.project_root)

                            if not verify_cmds:
                                # 🆕 V3.1：推論失敗 → 明確記錄 skip
                                state.metadata["pregate_skip"] = True
                                state.metadata["pregate_skip_reason"] = "no_verify_commands_detected"
                                logger.info("⚠️ CLI Pre-Gate SKIPPED: no verify commands detected")
                            elif str(review_status_raw) != "REJECTED":
                                logger.info("🚦 CLI Pre-Gate Triggered: Running %d verify commands", len(verify_cmds))
                                pregate_passed, pregate_results = run_cli_pregate(
                                    self.engine.project_root, verify_cmds, timeout_per_cmd=60
                                )
                                state.metadata["cli_pregate_results"] = pregate_results
                                state.metadata["pregate_skip"] = False
                                state.metadata["verification_commands"] = verify_cmds
                                state.metadata["verification_exit_codes"] = [r["exit_code"] for r in pregate_results]

                                if not pregate_passed:
                                    review_status_raw = "REJECTED"
                                    result_object["cli_pregate_rejected"] = True
                                    logger.info("🚫 CLI Pre-Gate 攔截：強制退回修復重試")
                        except Exception as exc:
                            logger.debug("cli_pregate_skip: %s", exc)

                        # Log R (Repair) phase
                        self.engine._add_step_to_history(
                            state,
                            "R",
                            metadata={
                                "status": "executed",
                                "decision_id": current_decision_id,
                                "skill_id": current_skill_id,
                                "attempt": repair_attempts,
                            },
                        )

                        # Log A (Audit) phase explicitly for phase path consistency
                        state.current_phase = "A"
                        a_decision_id = register_phase_decision("A", "audit-review")
                        state.metadata["last_audit_decision_id"] = a_decision_id
                        state.metadata["last_repair_decision_id"] = current_decision_id
                        self.engine._add_step_to_history(
                            state,
                            "A",
                            metadata={"status": review_status_raw, "decision_id": a_decision_id, "skill_id": "audit-review"},
                        )

                        # 🆕 A 階段學習：預載歷史幻覺模式
                        try:
                            from nexus.learning.knowledge_index import KnowledgeIndex
                            ki = KnowledgeIndex(self.engine.project_root, use_embedding=True)
                            a_hints = ki.search_similar(task_desc, top_k=3, threshold=0.2, task_type=task_type)
                            known_phantoms = []
                            for fm, _ in a_hints:
                                known_phantoms.extend(fm.phantom_patterns)
                            if known_phantoms:
                                state.metadata["known_phantom_patterns"] = known_phantoms
                                if "missing_physical_proof" in known_phantoms:
                                    state.metadata["require_strict_proof"] = True
                                logger.info("🛡️ A 階段：預載 %d 個歷史幻覺模式", len(known_phantoms))
                        except Exception as exc:
                            logger.debug("a_phase_learning_skip: %s", exc)

                        with tracer.phase_span('A', task_id=task_id) as a_span:
                            status, audit_success = self.engine.ReviewStatusNormalizer.normalize(review_status_raw)
                            checks = int(state.metadata.get("anti_hallucination_checks", 0) or 0) + 1
                            state.metadata["anti_hallucination_checks"] = checks
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
                            state.metadata["phantom_success_reason"] = phantom_reason
                            state.metadata["anti_hallucination_block_count"] = int(
                                state.metadata.get("anti_hallucination_block_count", 0) or 0
                            ) + 1
                            NexusEventBus.publish("phantom_detected", {"task_id": state.task_id, "reason": phantom_reason})
                        elif audit_success:
                            state.metadata["anti_hallucination_pass_count"] = int(
                                state.metadata.get("anti_hallucination_pass_count", 0) or 0
                            ) + 1

                        proof_present = bool(
                            str(result_object.get("proof_type", "") or "")
                            and str(result_object.get("proof_value", "") or "")
                        )
                        try:
                            event = build_outcome_event(
                                task_id=state.task_id,
                                phase="R",
                                decision_id=current_decision_id,
                                skill_id=current_skill_id,
                                passed=bool(audit_success),
                                phantom_blocked=bool(phantom_reason),
                                repair_success=bool(audit_success),
                                retry_count=max(0, repair_attempts - 1),
                                proof_present=proof_present,
                                regression_pass_rate=100.0 if audit_success else 0.0,
                                pattern_reuse=float(state.metadata.get("pattern_reuse_rate", 0.0) or 0.0),
                                next_run_hit=float(state.metadata.get("next_run_hit_rate", 0.0) or 0.0),
                                metadata={
                                    "status": status,
                                    "audit_status": review_status_raw,
                                    "source": "pipeline.repair_audit",
                                },
                            )
                            append_skill_outcome_event(self.engine.project_root, event)
                        except Exception as exc:
                            logger.warning("skill_outcome_event_write_failed: %s", exc)

                        if audit_success:
                            success = True
                            break

                        if status == "REJECTED" and repair_attempts < self.engine.max_retries:
                            # 🆕 記錄拒絕原因，供 CycleAnalyzer 分析
                            rejection_history = list(state.metadata.get("rejection_history", []))
                            reason_tag = phantom_reason if phantom_reason else f"rejected:{review_status_raw}"
                            rejection_history.append(reason_tag)
                            state.metadata["rejection_history"] = rejection_history

                            state.metadata["last_audit_failure"] = (
                                f"phantom success: {phantom_reason}" if phantom_reason else f"rejected: {review_status_raw}"
                            )
                            pack["audit_feedback"] = state.metadata["last_audit_failure"]

                            # 🆕 V3 Escalation：連續失敗 ≥3 次且根因指向規劃問題 → 跳回 P
                            if repair_attempts >= 3:
                                try:
                                    from nexus.learning.cycle_analyzer import analyze_cycle
                                    mid_cycle = analyze_cycle(rejection_history)
                                    mid_root = mid_cycle.get("root_cause", "")
                                    if mid_root in ("scope_drift", "insufficient_diag"):
                                        esc_count = int(state.metadata.get("escalation_count", 0)) + 1
                                        state.metadata["escalation_count"] = esc_count

                                        # 🆕 V3.1：超過 2 次 escalation → 人工介入
                                        if esc_count > 2:
                                            logger.error("🛑 Max escalation reached (%d). Entering HUMAN_REVIEW.", esc_count)
                                            state.metadata["human_review_required"] = True
                                            state.metadata["human_review_reason"] = f"max_escalation:{mid_root}"
                                            NexusEventBus.publish("human_review_required", {
                                                "task_id": state.task_id,
                                                "root_cause": mid_root,
                                                "escalation_count": esc_count,
                                            })
                                            break

                                        logger.warning("📢 Escalation: R↔A loop root_cause=%s, jumping back to P", mid_root)
                                        state.metadata["escalation_triggered"] = True
                                        state.metadata["escalation_root_cause"] = mid_root
                                        NexusEventBus.publish("escalation_to_plan", {
                                            "task_id": state.task_id,
                                            "root_cause": mid_root,
                                            "attempt": repair_attempts,
                                        })
                                        break  # 跳出 R↔A，讓外層邏輯決定是否重進 P
                                except Exception as esc_exc:
                                    logger.debug("escalation_analysis_failed: %s", esc_exc)

                            logger.warning(f"🔄 Audit Rejected. Retrying repair (Status: {status})")
                            continue
                        else:
                            break

                    with tracer.phase_span('C', task_id=task_id) as c_span:
                        # --- C Stage: Crystallize ---
                        # 🆕 V3.1：escalation 不等於失敗，而是「需要重規劃」
                        escalation_triggered = bool(state.metadata.get("escalation_triggered"))
                        human_review = bool(state.metadata.get("human_review_required"))
                        state.metadata["pipeline_success"] = bool(success)
                        
                        raw_terminal_state = (
                            "HUMAN_REVIEW" if human_review
                            else "ESCALATED" if escalation_triggered
                            else "SUCCESS" if success
                            else "FAILED"
                        )
                        state.metadata["pipeline_terminal_state"] = raw_terminal_state
                    
                    from nexus.engine.pipeline_outcome import PipelineOutcome, PipelineTerminalState, HumanReviewHandoff
                    import dataclasses
                    
                    handoff = None
                    if human_review:
                        handoff = HumanReviewHandoff(
                            escalation_count=int(state.metadata.get("escalation_count", 0)),
                            last_root_cause=state.metadata.get("human_review_reason") or str(state.metadata.get("cycle_root_cause", "")),
                            rejection_history=list(state.metadata.get("rejection_history", [])),
                            sandbox_mode=state.metadata.get("sandbox_mode", "unknown"),
                            pregate_skip_reason=state.metadata.get("pregate_skip_reason", ""),
                            task_id=state.task_id,
                            trace_id=state.metadata.get("trace_id", ""),
                            terminal_state="HUMAN_REVIEW"
                        )
                    
                    outcome = PipelineOutcome(
                        terminal_state=PipelineTerminalState[raw_terminal_state],
                        exit_code=PipelineTerminalState[raw_terminal_state].value,
                        task_id=state.task_id,
                        trace_id=state.metadata.get("trace_id", ""),
                        handoff=handoff,
                        cycle_root_cause=str(state.metadata.get("cycle_root_cause", "")),
                        verification_exit_codes=list(state.metadata.get("verification_exit_codes", [])),
                        sandbox_mode=state.metadata.get("sandbox_mode", "unknown"),
                        pregate_skip=bool(state.metadata.get("pregate_skip", False))
                    )
                    
                    # Store serialized dict for easy consumption by coordinator
                    state.metadata["pipeline_outcome"] = dataclasses.asdict(outcome)

                    # 🆕 循環根因分析
                    try:
                        from nexus.learning.cycle_analyzer import analyze_cycle
                        cycle = analyze_cycle(state.metadata.get("rejection_history", []))
                        state.metadata["cycle_root_cause"] = cycle["root_cause"]
                        state.metadata["cycle_analysis"] = cycle
                    except Exception as exc:
                        logger.debug("c_phase_cycle_analysis_failed: %s", exc)

                    # 🆕 記錄 P 階段實際使用的策略（供下次 P 階段讀取）
                    state.metadata["plan_strategy_used"] = state.metadata.get("inherited_plan_strategy", "")

                    # 🆕 合併幻覺歷史
                    phantom_history = list(state.metadata.get("known_phantom_patterns", []))
                    if state.metadata.get("phantom_success_reason"):
                        phantom_history.append(state.metadata["phantom_success_reason"])
                    state.metadata["phantom_pattern_history"] = list(set(phantom_history))
                    
                    # 🆕 Bonus: Unified Outcome Schema V2
                    from nexus.core.outcome_schema import NexusOutcomeV2
                    from datetime import datetime, timezone
                    import os
                    
                    commit_sha = "unknown"
                    try:
                        import subprocess
                        commit_sha = subprocess.check_output(
                            ["git", "rev-parse", "HEAD"], cwd=str(self.engine.project_root), stderr=subprocess.DEVNULL
                        ).decode().strip()
                    except Exception:
                        pass
                        
                    outcome_v2 = NexusOutcomeV2(
                        task_id=state.task_id,
                        trace_id=state.metadata.get("trace_id", ""),
                        span_id=state.metadata.get("span_id", ""),
                        terminal_state=raw_terminal_state,
                        exit_code=PipelineTerminalState[raw_terminal_state].value,
                        sandbox_mode=state.metadata.get("sandbox_mode", "unknown"),
                        pregate_skip=bool(state.metadata.get("pregate_skip", False)),
                        pregate_skip_reason=state.metadata.get("pregate_skip_reason", ""),
                        trust_level="production" if success else "untrusted",
                        escalation_count=int(state.metadata.get("escalation_count", 0)),
                        verification_commands=list(state.metadata.get("verification_commands", [])),
                        verification_exit_codes=list(state.metadata.get("verification_exit_codes", [])),
                        cycle_root_cause=str(state.metadata.get("cycle_root_cause", "")),
                        rejection_history=list(state.metadata.get("rejection_history", [])),
                        phantom_patterns=list(set(phantom_history)),
                        commit_sha=commit_sha,
                        model_version=os.environ.get("NEXUS_MODEL", "unknown"),
                        timestamp=datetime.now(timezone.utc).isoformat()
                    )
                    
                    state.metadata["nexus_outcome_v2"] = dataclasses.asdict(outcome_v2)

                    if success:
                        state.current_phase = "C"
                        c_decision_id = register_phase_decision("C", "crystallize")
                        self.engine._add_step_to_history(
                            state, "C", metadata={"decision_id": c_decision_id, "skill_id": "crystallize"}
                        )
                        try:
                            c_event = build_outcome_event(
                                task_id=state.task_id,
                                phase="C",
                                decision_id=c_decision_id,
                                skill_id="crystallize",
                                passed=True,
                                phantom_blocked=False,
                                repair_success=True,
                                retry_count=max(0, repair_attempts - 1),
                                proof_present=bool(
                                    str(state.metadata.get("last_proof_type", "") or "")
                                    and str(state.metadata.get("last_proof_value", "") or "")
                                ),
                                regression_pass_rate=100.0,
                                pattern_reuse=float(state.metadata.get("pattern_reuse_rate", 0.0) or 0.0),
                                next_run_hit=float(state.metadata.get("next_run_hit_rate", 0.0) or 0.0),
                                metadata={"status": "COMPLETED", "audit_status": "APPROVED", "source": "pipeline.crystallize"},
                            )
                            append_skill_outcome_event(self.engine.project_root, c_event)

                            # --- Hermes Integration: Build Skill Artifact ---
                            try:
                                outcome_dict = c_event.to_dict() if hasattr(c_event, "to_dict") else vars(c_event)
                                outcome_dict["verification_commands"] = state.metadata.get("verification_commands", [])
                                outcome_dict["verification_exit_codes"] = state.metadata.get("verification_exit_codes", [])
                                outcome_dict["pregate_skip"] = state.metadata.get("pregate_skip", False)
                                outcome_dict["pregate_skip_reason"] = state.metadata.get("pregate_skip_reason", "")
                                outcome_dict["sandbox_mode"] = state.metadata.get("sandbox_mode", "unknown")
                                research_pack = state.metadata.get("research_pack")
                                repair_result = state.metadata.get("repair_result", {})

                                skill_md = build_skill_artifact(
                                    task_id=state.task_id,
                                    task_desc=getattr(state, "task_desc", state.task_id),
                                    research_pack=research_pack,
                                    repair_result=repair_result,
                                    outcome_event=outcome_dict
                                )

                                if skill_md:
                                    from nexus.learning.skill_store import SkillStore
                                    store = SkillStore(self.engine.project_root)
                                    store.save_skill(state.task_id, skill_md)
                                    state.metadata["generated_skill_path"] = str(self.engine.project_root / "skills" / "learned" / f"{state.task_id}.md")
                                    logger.info("✨ Generated skill artifact: %s", f"{state.task_id}.md")
                                    NexusEventBus.publish("skill_created", {"task_id": state.task_id, "skill_path": state.metadata["generated_skill_path"]})
                                    
                                    # --- Skill Sharing: Push to Registry ---
                                    try:
                                        import os
                                        enabled = os.environ.get("NEXUS_SKILL_SHARE_ENABLED", "1")
                                        if enabled == "1":
                                            exchange = SkillExchange(
                                                store=SkillStore(self.engine.project_root),
                                                registry=SkillRegistry(
                                                    self.engine.project_root / ".nexus" / "registry" / "shared_skills.db"
                                                )
                                            )
                                            pushed = exchange.push_local_to_registry(
                                                task_id=state.task_id,
                                                node_id=os.environ.get("NEXUS_NODE_ID", "local"),
                                            )
                                            if pushed:
                                                NexusEventBus.publish("skill_shared", {
                                                    "task_id": state.task_id,
                                                    "registry_path": str(exchange.registry.db_path),
                                                })
                                    except Exception as share_exc:
                                        logger.warning("skill_push_failed: %s", share_exc)
                            except Exception as artifact_exc:
                                logger.warning("skill_artifact_generation_failed: %s", artifact_exc)

                        except Exception as exc:
                            logger.warning("skill_outcome_event_write_failed: %s", exc)
                        self.engine.state_io.save_global_state(state)
                        self.engine.commander.next_step(status="completed", state=state)
                    else:
                        try:
                            fail_decision_id = register_phase_decision("C", "crystallize")
                            fail_event = build_outcome_event(
                                task_id=state.task_id,
                                phase="C",
                                decision_id=fail_decision_id,
                                skill_id="crystallize",
                                passed=False,
                                phantom_blocked=bool(state.metadata.get("phantom_success_reason")),
                                repair_success=False,
                                retry_count=max(0, repair_attempts - 1),
                                proof_present=bool(
                                    str(state.metadata.get("last_proof_type", "") or "")
                                    and str(state.metadata.get("last_proof_value", "") or "")
                                ),
                                regression_pass_rate=0.0,
                                pattern_reuse=float(state.metadata.get("pattern_reuse_rate", 0.0) or 0.0),
                                next_run_hit=float(state.metadata.get("next_run_hit_rate", 0.0) or 0.0),
                                metadata={"status": "FAILED", "audit_status": "REJECTED", "source": "pipeline.crystallize"},
                            )
                            append_skill_outcome_event(self.engine.project_root, fail_event)
                        except Exception as exc:
                            logger.warning("skill_outcome_event_write_failed: %s", exc)

                    # Health Evaluation
                    health_score = health_evaluator.evaluate(state, success)
                    logger.info(f"📊 Final Health: {health_score:.1f}% | Success: {success}")

                    self.engine.state_io.save_global_state(state)
                    # 🆕 V3.1：回傳值語義擴展
                    if state.metadata.get("pipeline_terminal_state") == "HUMAN_REVIEW":
                        logger.error("🛑 Pipeline 終止於 HUMAN_REVIEW，需人工介入")
                        from nexus.core.handoff_bundle import HandoffBundleWriter
                        writer = HandoffBundleWriter(self.engine.project_root)
                        writer.create(
                            triggering_phase="pipeline_terminal",
                            reason=state.metadata.get("human_review_reason", "HUMAN_REVIEW triggered"),
                            task_id=state.task_id,
                            trace_id=state.metadata.get("trace_id", ""),
                            decision_id=str(state.metadata.get("last_decision_id", "")),
                            agent_history=[h.phase for h in state.steps_history],
                            state_variables={
                                "escalation_count": state.metadata.get("escalation_count", 0),
                                "sandbox_mode": state.metadata.get("sandbox_mode", "unknown"),
                            },
                        )
                    elif state.metadata.get("pipeline_terminal_state") == "ESCALATED":
                        logger.warning("📢 Pipeline 終止於 ESCALATED，Coordinator 應重新規劃")
                    return success
