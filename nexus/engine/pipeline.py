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

logger = logging.getLogger(__name__)

class NexusPipeline:
    """⚙️ Nexus Task Pipeline (P-X-D-R-A-C)"""
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
        """執行核心 P-X-D-R-A-C 管線"""
        task_id = f"{task_type}-{int(time.time())}"
        state = NexusState(task_id=task_id)
        state.metadata["task_description"] = task_desc
        state.metadata.setdefault("phase_decisions", {})
        state.metadata.setdefault("phase_skills", {})
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
        self.engine.state_io.save_global_state(state) # 🛡️ Save before commander loads it
        self.engine.commander.next_step(status="started") # 🎯 Trinity Trigger
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

        # --- P Stage: Plan ---
        state.current_phase = "P"
        p_decision_id = register_phase_decision("P", "planner")
        decision = hub.make_pre_routing_decision(task_id, {"type": task_type, **(context or {})})
        prediction = planner.run(state, {"task": task_desc, **kwargs})
        accumulator.record(state, "P", prediction) # P phase recording
        self.engine._add_step_to_history(
            state,
            "P",
            metadata={"prediction": prediction, "decision_id": p_decision_id, "skill_id": "planner"},
        )

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
        self.engine._add_step_to_history(
            state,
            "D",
            metadata={"pack_keys": list(pack.keys()), "decision_id": d_decision_id, "skill_id": "diagnose-pack"},
        )

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
            repair_attempts += 1
            state.retry_count = max(state.retry_count, repair_attempts - 1)
            state.current_phase = "R"
            logger.info(f"🛠️ [Pipeline] Attempt {repair_attempts}/{self.engine.max_retries}")

            # R: Repair
            res = repairer.run(state, pack)
            accumulator.record(state, "R", res, overhead=100)
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
            else:
                result_object = {}
            
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
                logger.warning(f"🔄 Audit Rejected. Retrying repair (Status: {status})")
                continue
            else:
                break

        # --- C Stage: Crystallize ---
        state.metadata["pipeline_success"] = bool(success)
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
        return success
