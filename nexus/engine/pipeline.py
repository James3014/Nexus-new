import logging
import time
import json
from datetime import datetime
from typing import Dict, Any, Optional
from nexus.core.state_contracts import NexusState

logger = logging.getLogger(__name__)

class NexusPipeline:
    """⚙️ Nexus Task Pipeline (P-X-D-R-A-C)"""
    def __init__(self, engine):
        self.engine = engine

    def run(self, task_desc: str, task_type: str = "bug", context: Optional[Dict] = None, **kwargs) -> bool:
        """執行核心 P-X-D-R-A-C 管線"""
        task_id = f"{task_type}-{int(time.time())}"
        state = NexusState(task_id=task_id)
        
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
        decision = hub.make_pre_routing_decision(task_id, {"type": task_type, **(context or {})})
        prediction = planner.run(state, {"task": task_desc, **kwargs})
        accumulator.record(state, "P", prediction) # P phase recording
        self.engine._add_step_to_history(state, "P", metadata={"prediction": prediction})

        # --- X Stage: Research ---
        research_pack = None
        if research_policy.should_research(decision, task_desc):
            state.current_phase = "X"
            research_pack = researcher.run(state, {"task": task_desc})
            accumulator.record(state, "X", research_pack, overhead=50)
            self.engine._add_step_to_history(state, "X", metadata=research_pack)

        # --- D Stage: Diagnose ---
        state.current_phase = "D"
        if task_type == "bug":
            pack = hub.assemble_diag_pack([], task_desc)
        else:
            pack = hub.assemble_feature_pack(plan=prediction)
            
        if research_pack:
            pack["research_context"] = research_pack
        
        # 🧬 WP-1: Record D phase overhead and capture potential research tokens
        pack["token_capture_status"] = "ok"
        accumulator.record(state, "D", pack, overhead=50)
        self.engine._add_step_to_history(state, "D", metadata={"pack_keys": list(pack.keys())})

        # --- R/A Stage: Repair Loop ---
        repair_attempts = 0
        success = False
        while repair_attempts < self.engine.max_retries:
            repair_attempts += 1
            state.current_phase = "R"
            logger.info(f"🛠️ [Pipeline] Attempt {repair_attempts}/{self.engine.max_retries}")

            # R: Repair
            res = repairer.run(state, pack)
            accumulator.record(state, "R", res, overhead=100)
            
            # Robust extraction of status
            review_status_raw = "REJECTED"
            if isinstance(res, dict):
                review_status_raw = res.get("status", "REJECTED")
                state.metadata["last_review_status"] = review_status_raw
            
            # Log R (Repair) phase
            self.engine._add_step_to_history(state, "R", metadata={"status": "executed"})
            
            # Log A (Audit) phase explicitly for phase path consistency
            state.current_phase = "A"
            # 🧬 WP-1: Record A phase explicitly to capture status and overhead
            accumulator.record(state, "A", res, overhead=50)
            self.engine._add_step_to_history(state, "A", metadata={"status": review_status_raw})
            
            status, audit_success = self.engine.ReviewStatusNormalizer.normalize(review_status_raw)
            result_object = res.get("result_object", {}) if isinstance(res, dict) else {}
            patch_generated = bool(result_object.get("patch_generated"))
            no_change_reason = (result_object.get("no_change_reason") or "").strip()
            patch_apply_success = result_object.get("patch_apply_success")

            # Hard gate against phantom success:
            # - If patch was generated, it must be applied successfully.
            # - If no patch was generated, PASS must carry an explicit reason.
            if audit_success:
                if patch_generated and patch_apply_success is False:
                    logger.error("❌ [Gate] Audit PASS blocked: patch apply failed.")
                    audit_success = False
                    status = "REJECTED"
                elif not patch_generated and not no_change_reason:
                    logger.error("❌ [Gate] Audit PASS blocked: missing no_change_reason.")
                    audit_success = False
                    status = "REJECTED"

            if audit_success:
                success = True
                break
            
            if status == "REJECTED" and repair_attempts < self.engine.max_retries:
                logger.warning(f"🔄 Audit Rejected. Retrying repair (Status: {status})")
                continue
            else:
                break

        # --- C Stage: Crystallize ---
        if success:
            state.current_phase = "C"
            self.engine.commander.crystallize(state)
            self.engine._add_step_to_history(state, "C")

        # 🧬 Phase Health Autonomy: Update and Capture
        from nexus.core.phase_health import PhaseHealthCalculator
        PhaseHealthCalculator.update_state(state)

        # Health Evaluation
        health_score = health_evaluator.evaluate(state, success)
        logger.info(f"📊 Final Health: {health_score:.1f}% | Success: {success} | Pipeline Health: {state.pipeline_health}%")
        
        self.engine.state_io.save_global_state(state)
        
        # 📂 WP-1: Save run-specific phase metrics
        try:
            run_dir = self.engine.run_dir / "phase_metrics"
            run_dir.mkdir(parents=True, exist_ok=True)
            run_file = run_dir / f"{state.task_id}_metrics.json"
            
            payload = {
                "task_id": state.task_id,
                "timestamp": datetime.now().isoformat(),
                "pipeline_health": state.pipeline_health,
                "metrics": {p: m.dict() for p, m in state.phase_metrics.items()}
            }
            run_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.error(f"❌ [WP-1] Failed to save phase metrics: {e}")

        return success
