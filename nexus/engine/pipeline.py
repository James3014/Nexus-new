import logging
import time
from typing import Dict, Any, Optional
from nexus.delivery.phantom_guard import detect_inconclusive_success
from nexus.core.state_contracts import NexusState
from nexus.core.skill_outcomes import build_outcome_event, append_skill_outcome_event

logger = logging.getLogger(__name__)

class NexusPipeline:
    """⚙️ Nexus Task Pipeline (P-X-D-R-A-C)"""
    def __init__(self, engine):
        self.engine = engine

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
        if not dry_run_mode and (force_research or research_policy.should_research(decision, task_desc)):
            state.current_phase = "X"
            x_decision_id = register_phase_decision("X", "researcher")
            research_pack = researcher.run(state, {"task": task_desc})
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
