import logging
import time
from typing import Dict, Any, Optional
from nexus.delivery.phantom_guard import detect_inconclusive_success
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
        state.metadata["task_description"] = task_desc
        if context:
            state.metadata.update(context)
        
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
        decision = hub.make_pre_routing_decision(task_id, {"type": task_type, **(context or {})})
        prediction = planner.run(state, {"task": task_desc, **kwargs})
        accumulator.record(state, "P", prediction) # P phase recording
        self.engine._add_step_to_history(state, "P", metadata={"prediction": prediction})

        # --- X Stage: Research ---
        research_pack = None
        force_research = bool(state.metadata.get("benchmark_force_research"))
        if force_research or research_policy.should_research(decision, task_desc):
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
                result_object = res.get("result_object", {})
            else:
                result_object = {}
            
            # Log R (Repair) phase
            self.engine._add_step_to_history(state, "R", metadata={"status": "executed"})
            
            # Log A (Audit) phase explicitly for phase path consistency
            state.current_phase = "A"
            self.engine._add_step_to_history(state, "A", metadata={"status": review_status_raw})
            
            status, audit_success = self.engine.ReviewStatusNormalizer.normalize(review_status_raw)
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
            self.engine._add_step_to_history(state, "C")
            self.engine.state_io.save_global_state(state)
            self.engine.commander.next_step(status="completed", state=state)

        # Health Evaluation
        health_score = health_evaluator.evaluate(state, success)
        logger.info(f"📊 Final Health: {health_score:.1f}% | Success: {success}")
        
        self.engine.state_io.save_global_state(state)
        return success
