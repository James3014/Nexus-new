from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any

from nexus.delivery.phantom_guard import detect_inconclusive_success
from nexus.events.transport import NexusEventBus
from nexus.core.protocols import PipelineContextProtocol


logger = logging.getLogger(__name__)


def evaluate_audit_result(
    owner: Any,
    ctx: PipelineContextProtocol,
    eval_ctx: Any,
    *,
    phantom_detector: Any = detect_inconclusive_success,
) -> dict[str, Any]:
    """Evaluates audit results (Phase A) and detects phantom successes."""
    ctx.state.current_phase = "A"
    review_status_raw = eval_ctx.review_status_raw
    result_object = eval_ctx.result_object
    # Keep this flag round-scoped; stale rejections must not poison later passes.
    ctx.state.metadata.pop("evidence_trust_rejection", None)

    a_decision_id = owner._register_phase_decision(ctx, "A", "audit-review")
    ctx.state.metadata["last_audit_decision_id"] = a_decision_id
    ctx.state.metadata["last_repair_decision_id"] = eval_ctx.current_decision_id

    owner.engine._add_step_to_history(
        ctx.state, "A", metadata={"status": review_status_raw, "decision_id": a_decision_id, "skill_id": "audit-review"},
    )

    owner._load_audit_hints(ctx)

    with eval_ctx.tracer.phase_span('A', task_id=ctx.task_id) as a_span:
        # Normalize status to canonical forms (APPROVED/REJECTED)
        status, audit_success = owner.engine.ReviewStatusNormalizer.normalize(review_status_raw)
        
        # Update hallucination check counters safely
        owner._update_meta_counter(ctx, "anti_hallucination_checks")
        mock_env = owner._is_mock_engine_environment()

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
                cwd=owner.engine.project_root, capture_output=True, text=True
            )
            _physical_has_changes = bool(_diff_result.stdout.strip())
            
            # 物理上沒有變動，不論 Agent 說什麼都視為 False
            physical_patch_generated = _physical_has_changes
            physical_patch_applied = _physical_has_changes
            verify_commands_executed = bool(ctx.state.metadata.get("cli_pregate_results"))

        # Detect phantom success (status=APPROVED but no evidence)
        phantom_reason = phantom_detector(
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
                    diff_cmd = subprocess.run(["git", "diff", "--name-only"], cwd=owner.engine.project_root, capture_output=True, text=True)
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
        owner._update_meta_counter(ctx, "anti_hallucination_block_count")
        NexusEventBus.publish("phantom_detected", {"task_id": ctx.state.task_id, "reason": phantom_reason})

    # === NEW: Independent Evidence Verification ===
    if mock_env:
        # Keep fail-closed verifier semantics even in mock environments.
        try:
            from nexus.delivery.evidence_verifier import EvidenceVerifier
            verifier = EvidenceVerifier(owner.engine.project_root)
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
            owner._update_meta_counter(ctx, "anti_hallucination_pass_count")
        owner._record_repair_outcome_event(
            ctx, eval_ctx.repair_attempts, audit_success, phantom_reason, result_object,
            eval_ctx.current_decision_id, eval_ctx.current_skill_id, status, review_status_raw
        )
        return {"audit_success": audit_success, "status": status, "phantom_reason": phantom_reason}

    from nexus.delivery.evidence_verifier import EvidenceVerifier

    try:
        verifier = EvidenceVerifier(owner.engine.project_root)
        evidence_path = owner.engine.project_root / ".nexus" / "reports" / "hallucination_evidence.json"
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
        owner._update_meta_counter(ctx, "anti_hallucination_pass_count")

    # Capture skill outcome for long-term learning
    owner._record_repair_outcome_event(
        ctx, eval_ctx.repair_attempts, audit_success, phantom_reason, result_object,
        eval_ctx.current_decision_id, eval_ctx.current_skill_id, status, review_status_raw
    )

    return {"audit_success": audit_success, "status": status, "phantom_reason": phantom_reason}
