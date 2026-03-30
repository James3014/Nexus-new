import logging
import time
import subprocess
from dataclasses import dataclass
from nexus.learning.knowledge_index import KnowledgeIndex
from nexus.core.event_bus import NexusEventBus
from typing import Any, Dict, List, Optional
from nexus.core.protocols import PipelineContextProtocol
from nexus.engine.cli_pregate import run_cli_pregate, _auto_detect_verify_commands
from nexus.delivery.phantom_guard import detect_inconclusive_success
from nexus.core.skill_outcomes import build_outcome_event, append_skill_outcome_event
from nexus.learning.cycle_analyzer import analyze_cycle

logger = logging.getLogger(__name__)

@dataclass
class AuditEvalContext:
    """A 階段審計評估的參數封裝。"""
    tracer: Any
    repair_attempts: int
    review_status_raw: str
    result_object: dict
    current_decision_id: str
    current_skill_id: str

class PipelineRepairMixin:
    """🛠️ Mixin for Repair/Audit loop logic in NexusPipeline."""
    
    def _execute_single_repair(self, ctx: PipelineContextProtocol, tracer: Any, repair_attempts: int) -> dict:
        """執行單次修復嘗試（R 階段）。"""
        self._prepare_repair_context(ctx, repair_attempts)
        
        with tracer.phase_span('R', task_id=ctx.task_id) as r_span:
            res = ctx.repairer.run(ctx.state, ctx.pack)
            ctx.accumulator.record(ctx.state, "R", res, overhead=100)
            
        r_out = self._process_repair_response(ctx, res, repair_attempts)
        
        # Pregate 驗證
        if r_out["status"] != "REJECTED":
            r_out["status"] = self._run_pregate_if_needed(ctx, r_out["status"], r_out["result"])
            
        self.engine._add_step_to_history(
            ctx.state, "R", 
            metadata={
                "status": "executed", 
                "decision_id": r_out["current_decision_id"], 
                "skill_id": r_out["current_skill_id"], 
                "attempt": repair_attempts
            }
        )
        return r_out

    def _prepare_repair_context(self, ctx: PipelineContextProtocol, repair_attempts: int) -> None:
        """準備修復所需的上下文（RCA、技能 context）。"""
        if repair_attempts >= 2:
            ctx.pack["force_deep_diagnosis"] = True
            logger.info("🩺 連續失敗 ≥2，強制深度診斷")
            NexusEventBus.publish("repair_failed", {"task_id": ctx.state.task_id, "attempt": repair_attempts})

        try:
            learned = ctx.pack.get("learned_skills", [])
            if learned and learned[0].get("score", 0) >= 0.3:
                best_skill_id = learned[0]["skill_id"]
                ki = KnowledgeIndex(self.engine.project_root)
                full_skill = ki.load_full_skill(best_skill_id)
                if full_skill:
                    ctx.pack["skill_context"] = full_skill[:2000]
                    ctx.state.metadata["skill_context_loaded"] = best_skill_id
                    logger.info("📚 Loaded skill context: %s", best_skill_id)
        except (ImportError, FileNotFoundError, ValueError, Exception) as skill_ctx_exc:
            logger.warning("skill_context_load_fallback: %s", skill_ctx_exc)

    def _process_repair_response(self, ctx: PipelineContextProtocol, res: Any, repair_attempts: int) -> dict:
        """解析修復器的回應並更新元數據。"""
        current_decision_id = str((ctx.state.metadata.get("phase_decisions", {}) or {}).get("R") or self._register_phase_decision(ctx, "R", "default-repair"))
        current_skill_id = str((ctx.state.metadata.get("phase_skills", {}) or {}).get("R") or "default-repair")
        
        review_status_raw = "REJECTED"
        result_object = {}
        
        if isinstance(res, dict):
            review_status_raw = res.get("status", "REJECTED")
            ctx.state.metadata["last_review_status"] = review_status_raw
            result_object = res.get("result_object", {})
            self._map_repair_metadata(ctx, result_object)
        elif isinstance(res, list):
            self._process_repair_signals(ctx, res)

        return {
            "status": review_status_raw, "result": result_object, 
            "current_decision_id": current_decision_id, "current_skill_id": current_skill_id
        }

    def _map_repair_metadata(self, ctx: PipelineContextProtocol, result_object: dict) -> None:
        mapping = {
            "patch_generated": "last_patch_generated", "patch_apply_success": "last_patch_apply_success",
            "no_change_reason": "last_no_change_reason", "proof_type": "last_proof_type",
            "proof_value": "last_proof_value", "sandbox_mode": "sandbox_mode"
        }
        for res_key, meta_key in mapping.items():
            if res_key in result_object:
                ctx.state.metadata[meta_key] = result_object[res_key]

        audit_meta = result_object.get("audit_metadata", {})
        if audit_meta.get("verify_commands"):
            ctx.state.metadata["verification_commands"] = audit_meta["verify_commands"]
        if audit_meta.get("return_codes"):
            ctx.state.metadata["verification_exit_codes"] = list(audit_meta["return_codes"].values())

    def _process_repair_signals(self, ctx: PipelineContextProtocol, res: list) -> None:
        latest_res = res[-1] if res else {}
        for key in ["scope_drift", "insufficient_diag"]:
            if isinstance(latest_res, dict) and key in latest_res:
                ctx.pack[key] = latest_res[key]
                if "signals" not in ctx.state.metadata:
                    ctx.state.metadata["signals"] = {}
                ctx.state.metadata["signals"][key] = latest_res[key]

    def _run_pregate_if_needed(self, ctx: PipelineContextProtocol, current_status: str, result_object: dict) -> str:
        """執行 CLI Pregate 驗證。"""
        try:
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
                return current_status
            
            logger.info("🚦 CLI Pre-Gate Triggered: Running %d verify commands", len(verify_cmds))
            passed, results = run_cli_pregate(self.engine.project_root, verify_cmds, timeout_per_cmd=60)
            
            ctx.state.metadata["cli_pregate_results"] = results
            ctx.state.metadata["pregate_skip"] = False
            ctx.state.metadata["verification_commands"] = verify_cmds
            ctx.state.metadata["verification_exit_codes"] = [r["exit_code"] for r in results]

            if not passed:
                result_object["cli_pregate_rejected"] = True
                logger.info("🚫 CLI Pre-Gate 攔截：強制退回修復重試")
                return "REJECTED"
                
        except (subprocess.TimeoutExpired, OSError, ValueError) as exc:
            logger.debug("cli_pregate_skip: %s", exc)
            
        return current_status

    def _evaluate_audit_result(self, ctx: PipelineContextProtocol, eval_ctx: AuditEvalContext) -> dict:
        """評估審計結果（A 階段）。"""
        ctx.state.current_phase = "A"
        review_status_raw = eval_ctx.review_status_raw
        result_object = eval_ctx.result_object
        
        a_decision_id = self._register_phase_decision(ctx, "A", "audit-review")
        ctx.state.metadata["last_audit_decision_id"] = a_decision_id
        ctx.state.metadata["last_repair_decision_id"] = eval_ctx.current_decision_id
        
        self.engine._add_step_to_history(
            ctx.state, "A", metadata={"status": review_status_raw, "decision_id": a_decision_id, "skill_id": "audit-review"},
        )

        self._load_audit_hints(ctx)

        with eval_ctx.tracer.phase_span('A', task_id=ctx.task_id) as a_span:
            status, audit_success = self.engine.ReviewStatusNormalizer.normalize(review_status_raw)
            ctx.state.metadata["anti_hallucination_checks"] = int(ctx.state.metadata.get("anti_hallucination_checks", 0) or 0) + 1
            
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
            ctx.state.metadata["anti_hallucination_block_count"] = int(ctx.state.metadata.get("anti_hallucination_block_count", 0) or 0) + 1
            NexusEventBus.publish("phantom_detected", {"task_id": ctx.state.task_id, "reason": phantom_reason})
        elif audit_success:
            ctx.state.metadata["anti_hallucination_pass_count"] = int(ctx.state.metadata.get("anti_hallucination_pass_count", 0) or 0) + 1

        self._record_repair_outcome_event(
            ctx, eval_ctx.repair_attempts, audit_success, phantom_reason, result_object, 
            eval_ctx.current_decision_id, eval_ctx.current_skill_id, status, review_status_raw
        )

        return {"audit_success": audit_success, "status": status, "phantom_reason": phantom_reason}

    def _load_audit_hints(self, ctx: PipelineContextProtocol) -> None:
        """預載審計提示（歷史幻覺模式）。"""
        try:
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

    def _record_repair_outcome_event(self, ctx: PipelineContextProtocol, repair_attempts: int, audit_success: bool, phantom_reason: str, result_object: dict, current_decision_id: str, current_skill_id: str, status: str, review_status_raw: str) -> None:
        """記錄修復結果事件。"""
        proof_present = bool(str(result_object.get("proof_type", "") or "") and str(result_object.get("proof_value", "") or ""))
        try:
            from nexus.core.skill_outcomes import OutcomePayload
            payload = OutcomePayload(
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
                metadata={"status": status, "audit_status": review_status_raw, "source": "pipeline.repair_audit"},
            )
            event = build_outcome_event(payload)
            append_skill_outcome_event(self.engine.project_root, event)
        except (OSError, RuntimeError, ValueError) as exc:
            logger.warning("skill_outcome_event_write_failed: %s", exc)

    def _handle_escalation(self, ctx: PipelineContextProtocol, repair_attempts: int, review_status_raw: str, phantom_reason: str) -> bool:
        """處理審計失敗後的升級邏輯。"""
        rejection_history = list(ctx.state.metadata.get("rejection_history", []))
        reason_tag = phantom_reason if phantom_reason else f"rejected:{review_status_raw}"
        rejection_history.append(reason_tag)
        ctx.state.metadata["rejection_history"] = rejection_history

        ctx.state.metadata["last_audit_failure"] = f"phantom success: {phantom_reason}" if phantom_reason else f"rejected: {review_status_raw}"
        ctx.pack["audit_feedback"] = ctx.state.metadata["last_audit_failure"]

        if repair_attempts >= 3:
            try:
                mid_cycle = analyze_cycle(rejection_history)
                mid_root = mid_cycle.get("root_cause", "")
                if mid_root in ("scope_drift", "insufficient_diag"):
                    return self._perform_escalation(ctx, mid_root, repair_attempts)
            except (ValueError, TypeError, KeyError) as esc_exc:
                logger.debug("escalation_analysis_failed: %s", esc_exc)
        return False

    def _perform_escalation(self, ctx: PipelineContextProtocol, mid_root: str, repair_attempts: int) -> bool:
        """執行具體的升級動作。"""
        esc_count = int(ctx.state.metadata.get("escalation_count", 0)) + 1
        ctx.state.metadata["escalation_count"] = esc_count

        if esc_count > 2:
            logger.error("🛑 Max escalation reached (%d). Entering HUMAN_REVIEW.", esc_count)
            ctx.state.metadata["human_review_required"] = True
            ctx.state.metadata["human_review_reason"] = f"max_escalation:{mid_root}"
            NexusEventBus.publish("human_review_required", {"task_id": ctx.state.task_id, "root_cause": mid_root, "escalation_count": esc_count})
            return True

        logger.warning("📢 Escalation: R↔A loop root_cause=%s, jumping back to P", mid_root)
        ctx.state.metadata["escalation_triggered"] = True
        ctx.state.metadata["escalation_root_cause"] = mid_root
        NexusEventBus.publish("escalation_to_plan", {"task_id": ctx.state.task_id, "root_cause": mid_root, "attempt": repair_attempts})
        return True

    def _repair_audit_loop(self, ctx: PipelineContextProtocol, tracer: Any) -> bool:
        """主迴圈：R↔A 迭代。"""
        if ctx.dry_run:
            return self._execute_dry_run_repair(ctx)

        repair_attempts = 0
        success = False
        while repair_attempts < self.engine.max_retries:
            if self._check_external_interrupt(ctx):
                break

            repair_attempts += 1
            ctx.state.retry_count = max(ctx.state.retry_count, repair_attempts - 1)
            ctx.state.current_phase = "R"
            logger.info(f"🛠️ [Pipeline] Attempt {repair_attempts}/{self.engine.max_retries}")

            # 1. 修復
            r_out = self._execute_single_repair(ctx, tracer, repair_attempts)
            
            # 2. 審計
            eval_ctx = AuditEvalContext(
                tracer=tracer,
                repair_attempts=repair_attempts,
                review_status_raw=r_out["status"],
                result_object=r_out["result"],
                current_decision_id=r_out["current_decision_id"],
                current_skill_id=r_out["current_skill_id"]
            )
            a_out = self._evaluate_audit_result(ctx, eval_ctx)
            
            if a_out["audit_success"]:
                success = True
                break

            # 3. 處理失敗與升級
            if a_out["status"] == "REJECTED" and repair_attempts < self.engine.max_retries:
                if self._handle_escalation(ctx, repair_attempts, r_out["status"], a_out["phantom_reason"]):
                    break
                logger.warning(f"🔄 Audit Rejected. Retrying repair (Status: {a_out['status']})")
                continue
            else:
                break
                
        return success

    def _execute_dry_run_repair(self, ctx: PipelineContextProtocol) -> bool:
        """執行 Dry Run 模式的修復模擬。"""
        ctx.state.retry_count = 0
        ctx.state.current_phase = "R"
        r_dec_id = self._register_phase_decision(ctx, "R", "dry-run-repair")
        self._mock_dry_run_state(ctx)
        
        self.engine._add_step_to_history(
            ctx.state, "R", metadata={"status": "executed", "decision_id": r_dec_id, "skill_id": "dry-run-repair", "attempt": 1, "dry_run_mode": True}
        )
        
        ctx.state.current_phase = "A"
        a_dec_id = self._register_phase_decision(ctx, "A", "audit-review")
        self.engine._add_step_to_history(
            ctx.state, "A", metadata={"status": "APPROVED", "decision_id": a_dec_id, "skill_id": "audit-review", "dry_run_mode": True}
        )
        
        self._record_dry_run_outcome(ctx, r_dec_id)
        return True

    def _mock_dry_run_state(self, ctx: PipelineContextProtocol) -> None:
        ctx.state.metadata.update({
            "last_review_status": "APPROVED", "last_patch_generated": False,
            "last_patch_apply_success": True, "last_no_change_reason": "dry_run_mode",
            "last_proof_type": "", "last_proof_value": ""
        })

    def _record_dry_run_outcome(self, ctx: PipelineContextProtocol, r_dec_id: str) -> None:
        try:
            from nexus.core.skill_outcomes import OutcomePayload
            payload = OutcomePayload(
                task_id=ctx.state.task_id, phase="R", decision_id=r_dec_id,
                skill_id="dry-run-repair", passed=True, phantom_blocked=False,
                repair_success=True, retry_count=0, proof_present=False,
                regression_pass_rate=100.0,
                pattern_reuse=float(ctx.state.metadata.get("pattern_reuse_rate", 0.0) or 0.0),
                next_run_hit=float(ctx.state.metadata.get("next_run_hit_rate", 0.0) or 0.0),
                metadata={"status": "APPROVED", "audit_status": "APPROVED", "source": "pipeline.dry_run"}
            )
            append_skill_outcome_event(self.engine.project_root, build_outcome_event(payload))
        except Exception as exc:
            logger.warning("dry_run_outcome_record_failed: %s", exc)

    def _check_external_interrupt(self, ctx: PipelineContextProtocol) -> bool:
        """檢查外部中斷信號。"""
        external_signals = NexusEventBus.drain_signals("force_replan")
        if external_signals:
            logger.warning("📡 External signal received: force_replan. Breaking R↔A loop.")
            ctx.state.metadata["external_force_replan"] = True
            return True
        return False
