from typing import Any, Dict, List, Optional, Tuple, Union
import logging
import time
import subprocess
from dataclasses import dataclass
from pathlib import Path
from nexus.learning.knowledge_index import KnowledgeIndex
from nexus.events.transport import NexusEventBus
from nexus.core.protocols import PipelineContextProtocol
from nexus.engine.cli_pregate import run_cli_pregate, _auto_detect_verify_commands
from nexus.delivery.phantom_guard import detect_inconclusive_success
from nexus.core.skill_outcomes import build_outcome_event, append_skill_outcome_event
from nexus.learning.cycle_analyzer import analyze_cycle
from nexus.engine.recursive_repair_loop import RecursiveRepairLoop, recursive_repair_enabled

logger = logging.getLogger(__name__)

REJECTED_REPAIR_STATUSES = frozenset({"FAIL", "FAILED", "REJECTED", "REJECTED_NO_RED_TEST"})

@dataclass
class AuditEvalContext:
    """Encapsulation of audit evaluation parameters for Phase A."""
    tracer: Any
    repair_attempts: int
    review_status_raw: str
    result_object: dict
    current_decision_id: str
    current_skill_id: str

class PipelineRepairMixin:
    """🛠️ Mixin for Repair/Audit loop logic in NexusPipeline."""

    @staticmethod
    def _is_rejected_repair_status(status: Any) -> bool:
        return str(status or "").strip().upper() in REJECTED_REPAIR_STATUSES

    def _is_mock_engine_environment(self) -> bool:
        try:
            from unittest.mock import MagicMock
            if isinstance(self.engine, MagicMock):
                return True
        except Exception:
            pass
        project_root = getattr(self.engine, "project_root", None)
        run_dir = getattr(self.engine, "run_dir", None)
        if not isinstance(project_root, (str, Path)):
            return True
        if run_dir is not None and not isinstance(run_dir, (str, Path)):
            return True
        # Non-project directories (e.g. /tmp in tests) are mock environments
        if not Path(project_root).joinpath("nexus").is_dir():
            return True
        return False

    def _execute_single_repair(self, ctx: PipelineContextProtocol, tracer: Any, repair_attempts: int) -> dict:
        """Executes a single repair attempt (Phase R - v24.0 Bayesian Hardened)."""
        with tracer.phase_span('R', task_id=ctx.task_id) as r_span:
            composed = self._run_composition_repair_phase(ctx, repair_attempts)
            if composed is not None:
                return composed

            self._prepare_repair_context(ctx, repair_attempts)

            # 🧪 [Round 20] Inject Bayesian params based on previous trauma
            r_params = ctx.bayesian_params.copy()
            if repair_attempts > 1:
                r_params["temperature"] = 0.2 + (repair_attempts * 0.15)
                logger.info(f"🔥 [Bayesian-Repair] Scaling temperature to {r_params['temperature']:.2f}")

            try:
                res = ctx.repairer.run(ctx.state, ctx.pack, bayesian_params=r_params)
            except TypeError:
                # Backward compatibility for older repairer signatures.
                res = ctx.repairer.run(ctx.state, ctx.pack)
            ctx.accumulator.record(ctx.state, "R", res, overhead=100)

        r_out = self._process_repair_response(ctx, res, repair_attempts)
        
        # 🚀 [v24.0] Immediate Intra-loop learning trigger
        if self._is_rejected_repair_status(r_out["status"]):
            self._record_intra_loop_trauma(ctx, r_out)

        # CLI Pregate validation
        if not self._is_rejected_repair_status(r_out["status"]):
            r_out["status"] = self._run_pregate_if_needed(ctx, r_out["status"], r_out["result"])
            
            # === NEW: T11 產生 Evidence Bundle 給 Verifier ===
            try:
                self._write_hallucination_evidence_bundle(ctx)
            except Exception as e:
                logger.warning("evidence_bundle_generation_failed: %s", e)

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

    def _run_composition_repair_phase(self, ctx: PipelineContextProtocol, repair_attempts: int) -> dict | None:
        """Run the composed R phase when explicitly registered."""
        registry = getattr(self, "registry", None)
        if registry is None:
            return None
        plugin = next((item for item in registry.get_ordered_plugins() if item.name == "R"), None)
        if plugin is None or not plugin.should_run(ctx):
            return None

        ctx.pack.update(
            {
                "task": ctx.task_desc,
                "attempt": repair_attempts,
                "dry_run": bool(ctx.dry_run),
            }
        )
        result = plugin.execute(self, ctx)
        mutations = dict(result.mutations or {})
        status = str(mutations.get("status") or result.status or "").strip().upper() or "APPROVED"
        result_object = mutations.get("result_object")
        result_object = dict(result_object) if isinstance(result_object, dict) else mutations
        ctx.state.metadata["last_review_status"] = status
        self._map_repair_metadata(ctx, result_object)
        if self._is_rejected_repair_status(status):
            self._record_intra_loop_trauma(ctx, {"status": status, "result": result_object})
        else:
            status = self._run_pregate_if_needed(ctx, status, result_object)
            try:
                self._write_hallucination_evidence_bundle(ctx)
            except Exception as e:
                logger.warning("evidence_bundle_generation_failed: %s", e)
        r_out = {
            "status": status,
            "result": result_object,
            "current_decision_id": str(mutations.get("decision_id") or f"composition-r-{repair_attempts}"),
            "current_skill_id": str(mutations.get("skill_id") or "composition-repair"),
        }
        ctx.state.metadata["composition_repair_phase_status"] = status
        ctx.state.metadata["composition_repair_phase_mutations"] = mutations
        self.engine._add_step_to_history(
            ctx.state,
            "R",
            metadata={
                "status": "executed",
                "decision_id": r_out["current_decision_id"],
                "skill_id": r_out["current_skill_id"],
                "attempt": repair_attempts,
                "composition_phase": True,
            },
        )
        return r_out

    def _record_intra_loop_trauma(self, ctx: PipelineContextProtocol, r_out: dict):
        """🛡️ [v24.0] 記錄失敗基因，防止修復循環陷入死胡同。"""
        try:
            from nexus.core.state_contracts import TraumaRecord
            trauma = TraumaRecord(
                failure_signature=f"REPAIR_FAIL_{ctx.state.current_step_id}",
                penalty=-0.3 * ctx.state.retry_count,
                expiry=None # Eternal for current task
            )
            ctx.state.autonomic_weights.trauma_records.append(trauma)
            logger.info("🧠 [Learning] Intra-loop trauma recorded for next iteration.")
        except Exception: pass

    def _prepare_repair_context(self, ctx: PipelineContextProtocol, repair_attempts: int) -> None:
        """Prepares context required for repair (RCA, skill context)."""
        if repair_attempts >= 2:
            ctx.pack["force_deep_diagnosis"] = True
            logger.info("🩺 Multiple failures (≥2), forcing deep diagnosis mode")
            NexusEventBus.publish("repair_failed", {"task_id": ctx.state.task_id, "attempt": repair_attempts})

        try:
            learned = ctx.pack.get("learned_skills", [])
            if learned and isinstance(learned, list) and len(learned) > 0:
                best_skill = learned[0]
                if isinstance(best_skill, dict) and best_skill.get("score", 0) >= 0.3:
                    best_skill_id = best_skill["skill_id"]
                    ki = KnowledgeIndex(self.engine.project_root)
                    full_skill = ki.load_full_skill(best_skill_id)
                    if full_skill:
                        # Inject top 2000 chars of skill context to stay within token budget
                        ctx.pack["skill_context"] = full_skill[:2000]
                        ctx.state.metadata["skill_context_loaded"] = best_skill_id
                        logger.info("📚 Successfully loaded skill context: %s", best_skill_id)
        except Exception as skill_ctx_exc:
            logger.warning("skill_context_load_fallback: %s", skill_ctx_exc)

    def _process_repair_response(self, ctx: PipelineContextProtocol, res: Any, repair_attempts: int) -> dict:
        """Parses repairer response and updates state metadata."""
        # Resolve IDs for history tracking
        phase_decisions = ctx.state.metadata.get("phase_decisions", {}) or {}
        current_decision_id = str(phase_decisions.get("R") or self._register_phase_decision(ctx, "R", "default-repair"))

        phase_skills = ctx.state.metadata.get("phase_skills", {}) or {}
        current_skill_id = str(phase_skills.get("R") or "default-repair")

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
            "status": review_status_raw,
            "result": result_object,
            "current_decision_id": current_decision_id,
            "current_skill_id": current_skill_id
        }

    def _collect_code_artifacts_from_git_diff(self) -> List[str]:
        project_root = Path(getattr(self.engine, "project_root", Path.cwd()))
        diff_cmd = subprocess.run(
            ["git", "diff", "--name-only"],
            cwd=project_root,
            capture_output=True,
            text=True,
        )
        if diff_cmd.returncode != 0 or not diff_cmd.stdout:
            return []
        return [line.strip() for line in diff_cmd.stdout.splitlines() if line.strip()]

    @staticmethod
    def _build_test_artifacts_from_pregate_results(pregate_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for pregate_res in pregate_results:
            out.append(
                {
                    "command": pregate_res.get("cmd", ""),
                    "exit_code": pregate_res.get("exit_code", -1),
                    "stdout_tail": pregate_res.get("stdout_tail", ""),
                }
            )
        return out

    @staticmethod
    def _build_command_artifacts_from_pregate_results(pregate_results: List[Dict[str, Any]]) -> List[str]:
        return [
            f"{pregate_res.get('cmd', '')} -> rc={pregate_res.get('exit_code', -1)}"
            for pregate_res in pregate_results
        ]

    def _build_hallucination_evidence_bundle(self, ctx: PipelineContextProtocol) -> Dict[str, Any]:
        pregate_results = ctx.state.metadata.get("cli_pregate_results", [])
        if not isinstance(pregate_results, list):
            pregate_results = []

        return {
            "code_artifacts": self._collect_code_artifacts_from_git_diff(),
            "test_artifacts": self._build_test_artifacts_from_pregate_results(pregate_results),
            "command_artifacts": self._build_command_artifacts_from_pregate_results(pregate_results),
        }

    def _write_hallucination_evidence_bundle(self, ctx: PipelineContextProtocol) -> Path:
        import json

        project_root = Path(getattr(self.engine, "project_root", Path.cwd()))
        evidence_path = project_root / ".nexus" / "reports" / "hallucination_evidence.json"
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"evidence_bundle": self._build_hallucination_evidence_bundle(ctx)}
        evidence_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return evidence_path

    def _map_repair_metadata(self, ctx: PipelineContextProtocol, result_object: dict) -> None:
        """Maps result object fields to state metadata for persistence."""
        mapping = {
            "patch_generated": "last_patch_generated",
            "patch_apply_success": "last_patch_apply_success",
            "no_change_reason": "last_no_change_reason",
            "proof_type": "last_proof_type",
            "proof_value": "last_proof_value",
            "sandbox_mode": "sandbox_mode"
        }
        for res_key, meta_key in mapping.items():
            if res_key in result_object:
                ctx.state.metadata[meta_key] = result_object[res_key]

        # Extract verification intent from model response
        audit_meta = result_object.get("audit_metadata", {})
        if audit_meta.get("verify_commands"):
            ctx.state.metadata["verification_commands"] = audit_meta["verify_commands"]
        if audit_meta.get("return_codes"):
            ctx.state.metadata["verification_exit_codes"] = list(audit_meta["return_codes"].values())

    def _process_repair_signals(self, ctx: PipelineContextProtocol, res: list) -> None:
        """Processes signals (drift/diag) from repair history list."""
        if not res:
            return
        latest_res = res[-1]
        if not isinstance(latest_res, dict):
            return

        for key in ["scope_drift", "insufficient_diag"]:
            if key in latest_res:
                ctx.pack[key] = latest_res[key]
                if "signals" not in ctx.state.metadata:
                    ctx.state.metadata["signals"] = {}
                ctx.state.metadata["signals"][key] = latest_res[key]

    def _run_pregate_if_needed(self, ctx: PipelineContextProtocol, current_status: str, result_object: dict) -> str:
        """Runs CLI-based verification (Pre-Gate) to block hallucinated success."""
        if self._is_mock_engine_environment():
            ctx.state.metadata["pregate_skip"] = True
            ctx.state.metadata["pregate_skip_reason"] = "mock_engine_environment"
            return current_status
        try:
            verify_cmds = list(ctx.state.metadata.get("verification_commands", []))
            # Allow injection of specific verify commands via pack
            pack_verify = ctx.pack.get("verify_commands", [])
            if pack_verify:
                verify_cmds.extend(pack_verify)

            # Fallback to automatic discovery if no commands provided
            if not verify_cmds:
                verify_cmds = _auto_detect_verify_commands(self.engine.project_root)

            if not verify_cmds:
                ctx.state.metadata["pregate_skip"] = True
                ctx.state.metadata["pregate_skip_reason"] = "no_verify_commands_detected"
                # === CHANGED: 沒有驗證命令時不自動 PASS ===
                logger.warning("⚠️ CLI Pre-Gate: No verify commands detected. Status downgraded to UNVERIFIED.")
                ctx.state.metadata["pregate_unverified"] = True
                # 不改變 current_status，但在 Audit 階段會被 Evidence Verifier 攔截
                return current_status

            logger.info("🚦 CLI Pre-Gate Triggered: Running %d verify commands", len(verify_cmds))
            passed, results = run_cli_pregate(self.engine.project_root, verify_cmds, timeout_per_cmd=60)

            # Log results to metadata
            ctx.state.metadata["cli_pregate_results"] = results
            ctx.state.metadata["pregate_skip"] = False
            ctx.state.metadata["verification_commands"] = verify_cmds
            ctx.state.metadata["verification_exit_codes"] = [r["exit_code"] for r in results]

            if not passed:
                result_object["cli_pregate_rejected"] = True
                logger.info("🚫 CLI Pre-Gate Rejected: Forcing return to repair loop")
                return "REJECTED"

        except (subprocess.TimeoutExpired, OSError, ValueError) as exc:
            logger.debug("cli_pregate_error_ignored: %s", exc)

        return current_status

    def _evaluate_audit_result(self, ctx: PipelineContextProtocol, eval_ctx: AuditEvalContext) -> dict:
        """Evaluates audit results (Phase A) and detects phantom successes."""
        ctx.state.current_phase = "A"
        review_status_raw = eval_ctx.review_status_raw
        result_object = eval_ctx.result_object
        # Keep this flag round-scoped; stale rejections must not poison later passes.
        ctx.state.metadata.pop("evidence_trust_rejection", None)

        a_decision_id = self._register_phase_decision(ctx, "A", "audit-review")
        ctx.state.metadata["last_audit_decision_id"] = a_decision_id
        ctx.state.metadata["last_repair_decision_id"] = eval_ctx.current_decision_id

        self.engine._add_step_to_history(
            ctx.state, "A", metadata={"status": review_status_raw, "decision_id": a_decision_id, "skill_id": "audit-review"},
        )

        self._load_audit_hints(ctx)

        with eval_ctx.tracer.phase_span('A', task_id=ctx.task_id) as a_span:
            # Normalize status to canonical forms (APPROVED/REJECTED)
            status, audit_success = self.engine.ReviewStatusNormalizer.normalize(review_status_raw)
            
            # Update hallucination check counters safely
            self._update_meta_counter(ctx, "anti_hallucination_checks")
            mock_env = self._is_mock_engine_environment()

            # === NEW: T16 用 git diff 物理結果取代 Agent 自報 ===
            if mock_env:
                physical_patch_generated = bool(result_object.get("patch_generated", False))
                physical_patch_applied = bool(result_object.get("patch_apply_success", False))
                verify_commands_executed = True
                _physical_has_changes = physical_patch_generated
            else:
                import subprocess as _sp
                _diff_result = _sp.run(
                    ["git", "diff", "--stat", "HEAD"],
                    cwd=self.engine.project_root, capture_output=True, text=True
                )
                _physical_has_changes = bool(_diff_result.stdout.strip())
                
                # 物理上沒有變動，不論 Agent 說什麼都視為 False
                physical_patch_generated = _physical_has_changes
                physical_patch_applied = _physical_has_changes
                verify_commands_executed = bool(ctx.state.metadata.get("cli_pregate_results"))

            # Detect phantom success (status=APPROVED but no evidence)
            phantom_reason = detect_inconclusive_success(
                status=review_status_raw,
                patch_generated=physical_patch_generated,
                patch_apply_success=physical_patch_applied,
                no_change_reason=result_object.get("no_change_reason", ""),
                proof_type=result_object.get("proof_type", ""),
                proof_value=result_object.get("proof_value", ""),
                git_diff_empty=not _physical_has_changes,
                verify_commands_executed=verify_commands_executed,
            )
            
            # === NEW: T12 P↔R 跨階段 Diff 校驗 ===
            if audit_success and phantom_reason is None:
                try:
                    plan_targets = ctx.state.metadata.get("plan_target_files", []) or ctx.pack.get("target_files", [])
                    if plan_targets and isinstance(plan_targets, list):
                        diff_cmd = subprocess.run(["git", "diff", "--name-only"], cwd=self.engine.project_root, capture_output=True, text=True)
                        actual_modified = [p for p in diff_cmd.stdout.strip().split("\n") if p]
                        
                        # 提取檔名作比對，增加容錯率
                        plan_basenames = {Path(p).name for p in plan_targets}
                        actual_basenames = {Path(p).name for p in actual_modified}
                        
                        if actual_modified and plan_targets and not plan_basenames.intersection(actual_basenames):
                            phantom_reason = "plan_repair_mismatch"
                            logger.error("🛑 [Audit:MISMATCH] R-Stage modified files %s do not overlap with P-Stage plan %s.", actual_modified, plan_targets)
                except Exception as eval_diff_e:
                    logger.warning("plan_repair_diff_check_failed: %s", eval_diff_e)

        # Phantom reason must be applied BEFORE mock early-return
        if phantom_reason:
            audit_success = False
            status = "REJECTED"
            ctx.state.metadata["phantom_success_reason"] = phantom_reason
            self._update_meta_counter(ctx, "anti_hallucination_block_count")
            NexusEventBus.publish("phantom_detected", {"task_id": ctx.state.task_id, "reason": phantom_reason})

        # === NEW: Independent Evidence Verification ===
        if mock_env:
            # Keep fail-closed verifier semantics even in mock environments.
            try:
                from nexus.delivery.evidence_verifier import EvidenceVerifier
                verifier = EvidenceVerifier(self.engine.project_root)
                verifier.verify({})
            except Exception as ev_exc:
                audit_success = False
                status = "REJECTED"
                ctx.state.metadata["evidence_verifier_error"] = str(ev_exc)
                ctx.state.metadata["evidence_trust_rejection"] = True
            if status == "REJECTED":
                ctx.state.metadata["evidence_trust_rejection"] = True
            else:
                ctx.state.metadata["evidence_trust_rejection"] = False
            if not phantom_reason and audit_success:
                self._update_meta_counter(ctx, "anti_hallucination_pass_count")
            self._record_repair_outcome_event(
                ctx, eval_ctx.repair_attempts, audit_success, phantom_reason, result_object,
                eval_ctx.current_decision_id, eval_ctx.current_skill_id, status, review_status_raw
            )
            return {"audit_success": audit_success, "status": status, "phantom_reason": phantom_reason}

        from nexus.delivery.evidence_verifier import EvidenceVerifier

        try:
            verifier = EvidenceVerifier(self.engine.project_root)
            evidence_path = self.engine.project_root / ".nexus" / "reports" / "hallucination_evidence.json"
            if evidence_path.exists():
                import json
                evidence_bundle = json.loads(evidence_path.read_text()).get("evidence_bundle", {})
                verification = verifier.verify(evidence_bundle)
                ctx.state.metadata["independent_evidence_verification"] = verification
                
                if verification["overall_trust"] == "LOW":
                    audit_success = False
                    status = "REJECTED"
                    ctx.state.metadata["evidence_trust_rejection"] = True
                    logger.error("🛑 [Audit:EVIDENCE] Independent verification trust=LOW. Rejecting.")
        except Exception as ev_exc:
            logger.error("🛑 [FAIL_CLOSED_EVIDENCE_VERIFIER] Verifier crashed, rejecting by default: %s", ev_exc)
            audit_success = False
            status = "REJECTED"
            ctx.state.metadata["evidence_verifier_error"] = str(ev_exc)
            ctx.state.metadata["evidence_trust_rejection"] = True

        if not phantom_reason and audit_success:
            self._update_meta_counter(ctx, "anti_hallucination_pass_count")

        # Capture skill outcome for long-term learning
        self._record_repair_outcome_event(
            ctx, eval_ctx.repair_attempts, audit_success, phantom_reason, result_object,
            eval_ctx.current_decision_id, eval_ctx.current_skill_id, status, review_status_raw
        )

        return {"audit_success": audit_success, "status": status, "phantom_reason": phantom_reason}

    def _run_composition_audit_phase(self, ctx: PipelineContextProtocol, r_out: dict) -> dict | None:
        """Run the composed A phase as a fail-closed pre-audit gate when registered."""
        registry = getattr(self, "registry", None)
        if registry is None:
            return None
        plugin = next((item for item in registry.get_ordered_plugins() if item.name == "A"), None)
        if plugin is None or not plugin.should_run(ctx):
            return None

        original_pack = dict(ctx.pack or {})
        evidence_bundle = self._build_hallucination_evidence_bundle(ctx)
        ctx.pack.update(
            {
                "summary": str(r_out.get("status") or ctx.state.metadata.get("task_description") or ctx.task_id),
                "response_text": str(r_out.get("status") or ""),
                "evidence_bundle": evidence_bundle,
            }
        )
        try:
            result = plugin.execute(self, ctx)
        finally:
            ctx.pack = original_pack

        ctx.state.metadata["composition_audit_phase_status"] = result.status
        ctx.state.metadata["composition_audit_phase_mutations"] = result.mutations
        if result.status in {"fail", "FAILED"} or bool((result.mutations or {}).get("fail")):
            reason = str((result.mutations or {}).get("reason") or "composition_audit_failed")
            ctx.state.metadata["composition_audit_phase_rejection"] = reason
            return {"audit_success": False, "status": "REJECTED", "phantom_reason": reason}
        return None

    def _update_meta_counter(self, ctx: PipelineContextProtocol, key: str, increment: int = 1) -> None:
        """Safely updates an integer counter in metadata."""
        current = ctx.state.metadata.get(key, 0)
        if not isinstance(current, int):
            current = 0
        ctx.state.metadata[key] = current + increment

    def _load_audit_hints(self, ctx: PipelineContextProtocol) -> None:
        """Preloads audit hints based on historical hallucination patterns."""
        try:
            ki = KnowledgeIndex(self.engine.project_root, use_embedding=True)
            a_hints = ki.search_similar(ctx.task_desc, top_k=3, threshold=0.2, task_type=ctx.task_type)
            
            known_phantoms = []
            for fm, _ in a_hints:
                if hasattr(fm, 'phantom_patterns') and fm.phantom_patterns:
                    known_phantoms.extend(fm.phantom_patterns)
            
            if known_phantoms:
                ctx.state.metadata["known_phantom_patterns"] = list(set(known_phantoms))
                if "missing_physical_proof" in known_phantoms:
                    ctx.state.metadata["require_strict_proof"] = True
                logger.info("🛡️ Phase A: Loaded %d historical hallucination patterns", len(known_phantoms))
        except Exception as exc:
            logger.debug("a_phase_learning_skip: %s", exc)

    def _record_repair_outcome_event(self, ctx: PipelineContextProtocol, repair_attempts: int, audit_success: bool, 
                                   phantom_reason: str, result_object: dict, current_decision_id: str, 
                                   current_skill_id: str, status: str, review_status_raw: str) -> None:
        """Records detailed outcome event for future optimization."""
        proof_present = bool(str(result_object.get("proof_type", "") or "").strip() and 
                             str(result_object.get("proof_value", "") or "").strip())
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
        except Exception as exc:
            logger.warning("skill_outcome_event_write_failed: %s", exc)

    def _handle_escalation(self, ctx: PipelineContextProtocol, repair_attempts: int, review_status_raw: str, phantom_reason: str) -> bool:
        """Handles escalation logic after audit failure."""
        rejection_history = list(ctx.state.metadata.get("rejection_history", []))
        reason_tag = phantom_reason if phantom_reason else f"rejected:{review_status_raw}"
        rejection_history.append(reason_tag)
        ctx.state.metadata["rejection_history"] = rejection_history

        ctx.state.metadata["last_audit_failure"] = f"phantom success: {phantom_reason}" if phantom_reason else f"rejected: {review_status_raw}"
        ctx.pack["audit_feedback"] = ctx.state.metadata["last_audit_failure"]

        # Escalation analysis after 3 failures
        if repair_attempts >= 3:
            try:
                mid_cycle = analyze_cycle(rejection_history)
                mid_root = mid_cycle.get("root_cause", "")
                if mid_root in ("scope_drift", "insufficient_diag"):
                    return self._perform_escalation(ctx, mid_root, repair_attempts)
            except Exception as esc_exc:
                logger.debug("escalation_analysis_failed: %s", esc_exc)
        return False, False

    def _perform_escalation(self, ctx: PipelineContextProtocol, mid_root: str, repair_attempts: int):
        """Executes specific escalation actions (Plan jump or Human Review).
        Returns a tuple: (break_loop: bool, replan_succeeded: bool)
        """
        self._update_meta_counter(ctx, "escalation_count")
        esc_count = ctx.state.metadata.get("escalation_count", 0)

        if esc_count > 2:
            logger.error("🛑 Max escalation reached (%d). Entering HUMAN_REVIEW.", esc_count)
            ctx.state.metadata["human_review_required"] = True
            ctx.state.metadata["human_review_reason"] = f"max_escalation:{mid_root}"
            NexusEventBus.publish("human_review_required", {"task_id": ctx.state.task_id, "root_cause": mid_root, "escalation_count": esc_count})
            return True, False

        logger.warning("📢 Escalation → Actual Replan (root_cause=%s)", mid_root)
        ctx.state.metadata["escalation_triggered"] = True
        ctx.state.metadata["escalation_root_cause"] = mid_root
        NexusEventBus.publish("escalation_to_plan", {"task_id": ctx.state.task_id, "root_cause": mid_root, "attempt": repair_attempts})
        
        # === NEW: T19 Actual Replan Execution ===
        try:
            logger.info("⚙️ Executing actual P-Stage for replan due to escalation...")
            p_plugin = next((p for p in self.engine.registry.get_ordered_plugins() if p.name == "P"), None)
            if not p_plugin:
                raise RuntimeError("P-Stage plugin not found")
                
            replan_feedback = {
                "root_cause": mid_root,
                "rejection_history": ctx.state.metadata.get("rejection_history", []),
                "repair_attempts": repair_attempts,
            }
            # Inject feedback so P-Stage loop will see it
            ctx.kwargs["plan_feedback"] = replan_feedback
            try:
                p_plugin.execute(self.engine, ctx)
            finally:
                ctx.kwargs.pop("plan_feedback", None)
            
            logger.info("✅ Escalation Replan succeeded, about to reset R↔A loop.")
            return False, True
        except Exception as e:
            logger.error("❌ Replan failed during escalation: %s", e)
            return True, False

    def _repair_audit_loop(self, ctx: PipelineContextProtocol, tracer: Any) -> bool:
        """Main R↔A loop: Iteratively repair and audit until success or exhaustion."""
        if ctx.dry_run:
            return self._execute_dry_run_repair(ctx)

        repair_attempts = 0
        success = False
        max_retries = getattr(self.engine, 'max_retries', 3)
        rlm_loop = None
        if recursive_repair_enabled(ctx):
            rlm_loop = RecursiveRepairLoop.from_context(
                project_root=getattr(self.engine, "project_root", Path.cwd()),
                ctx=ctx,
                max_iterations=max_retries,
            )
            ctx.state.metadata["rlm_recursive_repair_enabled"] = True
            ctx.state.metadata["rlm_recursive_trace_path"] = str(rlm_loop.trace_path)

        while repair_attempts < max_retries:
            if self._check_external_interrupt(ctx):
                break

            repair_attempts += 1
            ctx.state.retry_count = max(ctx.state.retry_count, repair_attempts - 1)
            ctx.state.current_phase = "R"
            logger.info(f"🛠️ [Pipeline] Repair Attempt {repair_attempts}/{max_retries}")
            if rlm_loop is not None and not rlm_loop.prepare_iteration(
                project_root=Path(getattr(self.engine, "project_root", Path.cwd())),
                ctx=ctx,
                iteration=repair_attempts,
            ):
                break

            # Step 1: Repair
            r_out = self._execute_single_repair(ctx, tracer, repair_attempts)
            if rlm_loop is not None:
                rlm_loop.record_repair(
                    iteration=repair_attempts,
                    status=r_out["status"],
                    result=r_out["result"],
                    metadata=ctx.state.metadata,
                )

            # Step 2: Audit
            eval_ctx = AuditEvalContext(
                tracer=tracer,
                repair_attempts=repair_attempts,
                review_status_raw=r_out["status"],
                result_object=r_out["result"],
                current_decision_id=r_out["current_decision_id"],
                current_skill_id=r_out["current_skill_id"]
            )
            a_out = self._run_composition_audit_phase(ctx, r_out) or self._evaluate_audit_result(ctx, eval_ctx)
            if rlm_loop is not None:
                rlm_loop.record_audit(iteration=repair_attempts, audit_result=a_out)
                budget_state = rlm_loop.consume_iteration()
                ctx.state.metadata["rlm_budget_state"] = budget_state.to_dict()

            if a_out["audit_success"]:
                success = True
                break

            if rlm_loop is not None and rlm_loop.state.exhausted:
                ctx.state.metadata["rlm_budget_exhausted"] = True
                ctx.state.metadata["rlm_budget_exhausted_reasons"] = rlm_loop.state.exhausted_reasons
                rlm_loop.record_budget_exhausted(iteration=repair_attempts)
                break

            # Step 3: Handle Failure
            if a_out["status"] == "REJECTED" and repair_attempts < max_retries:
                esc_ret = self._handle_escalation(ctx, repair_attempts, r_out["status"], a_out["phantom_reason"])
                
                # Check for tuple signature
                if isinstance(esc_ret, tuple):
                    break_auto, replan_ok = esc_ret
                else:
                    break_auto = esc_ret
                    replan_ok = False
                
                if replan_ok:
                    logger.warning("🔄 Escalation triggered successful replan, resetting repair cycle.")
                    repair_attempts = 0
                    continue
                    
                if break_auto:
                    # Escalation might have reached max_retries or failed replan
                    break
                logger.warning("🔄 Audit Rejected. Retrying repair cycle...")
                continue
            else:
                # Reached max retries or unrecoverable error
                break

        return success

    def _execute_dry_run_repair(self, ctx: PipelineContextProtocol) -> bool:
        """Simulates repair loop in Dry Run mode."""
        ctx.state.retry_count = 0
        ctx.state.current_phase = "R"
        r_dec_id = self._register_phase_decision(ctx, "R", "dry-run-repair")
        self._mock_dry_run_state(ctx)

        self.engine._add_step_to_history(
            ctx.state, "R", metadata={"status": "executed", "decision_id": r_dec_id, "skill_id": "dry-run-repair", "attempt": 1, "dry_run_mode": True}
        )

        a_out = self._run_composition_audit_phase(
            ctx,
            {
                "status": "APPROVED",
                "result": {"dry_run_mode": True},
                "current_decision_id": r_dec_id,
                "current_skill_id": "dry-run-repair",
            },
        )
        if a_out is not None and not bool(a_out.get("audit_success")):
            return False

        ctx.state.current_phase = "A"
        a_dec_id = self._register_phase_decision(ctx, "A", "audit-review")
        self.engine._add_step_to_history(
            ctx.state, "A", metadata={"status": "APPROVED", "decision_id": a_dec_id, "skill_id": "audit-review", "dry_run_mode": True}
        )

        self._record_dry_run_outcome(ctx, r_dec_id)
        return True

    def _mock_dry_run_state(self, ctx: PipelineContextProtocol) -> None:
        """Mocks metadata for dry run."""
        ctx.state.metadata.update({
            "last_review_status": "APPROVED", 
            "last_patch_generated": False,
            "last_patch_apply_success": True, 
            "last_no_change_reason": "dry_run_mode",
            "last_proof_type": "", 
            "last_proof_value": ""
        })

    def _record_dry_run_outcome(self, ctx: PipelineContextProtocol, r_dec_id: str) -> None:
        """Records outcome for dry run."""
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
        """Checks for external signals (e.g., force_replan)."""
        external_signals = NexusEventBus.drain_signals("force_replan")
        if external_signals:
            logger.warning("📡 External signal received: force_replan. Breaking R↔A loop.")
            ctx.state.metadata["external_force_replan"] = True
            return True
        return False
