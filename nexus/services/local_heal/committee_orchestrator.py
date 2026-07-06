from typing import Any, Callable, List, Dict
from copy import deepcopy
import hashlib
import logging
import os
import time
from nexus.services.local_heal.interface import IPhase, PhaseResult
from nexus.services.local_heal.context import HealContext
from nexus.services.local_heal.orchestrator import HealOrchestrator
from nexus.services.local_heal.output_understanding import build_output_understanding_result
from nexus.committee.controller import CommitteeControllerV263

COMMITTEE_ROUTE_SCHEMA = "nexus.local_heal.committee_trace.v1"
COMMITTEE_ROUTE_POLICY = "qwen_3b_judge_plus_qwen_7b_plus_deepseek_6_7b"
DIAGNOSIS_COMMITTEE_SCHEMA = "nexus.local_heal.committee_diagnosis.v1"
# DEPRECATED: Legacy test fixture constant. Do not use in runtime decision paths.
COMMITTEE_PROPOSER_SPECS = (
    {"model": "qwen2.5-coder:7b-instruct", "role": "primary"},
    {"model": "deepseek-coder:6.7b-instruct", "role": "secondary"},
)

logger = logging.getLogger(__name__)


def _compute_patch_hash(patch_text: str) -> str:
    return hashlib.sha256(patch_text.encode("utf-8")).hexdigest()[:16] if patch_text else ""


def _borda_select_diagnosis(diagnoses: list[dict]) -> dict | None:
    """Borda voting: aggregate confidence-weighted rankings, select best."""
    if not diagnoses:
        return None
    if len(diagnoses) == 1:
        return diagnoses[0]
    scored = []
    for d in diagnoses:
        conf = float(d.get("confidence", 0.5))
        rank = int(d.get("rank", len(diagnoses)))
        borda_score = conf * (len(diagnoses) - rank + 1)
        scored.append((borda_score, d))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1]


class CommitteeOrchestrator(HealOrchestrator):
    """
    🤝 Nexus Committee Orchestrator (v26)
    實施 Verifier-backed Committee Search。
    在 Patch Synthesis 階段進行多樣本採樣與 Borda 選優。
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.k = None

    def _invoke_diagnosis_model(self, model: str, ctx: HealContext) -> dict:
        """Invoke a single model for diagnosis. Returns diagnosis dict."""
        from nexus.services.local_heal.llm_client import OllamaLLMClient
        from nexus.engine.local_model_policy import LocalModelPolicy

        decision = LocalModelPolicy.select_model(
            task_type="swe_repair", phase="diagnosis",
            context={"reasoning_mode": getattr(ctx.op, "reasoning_mode", "INTUITIVE")},
        )
        timeout = decision.get("timeout_seconds", 120)
        options = decision.get("ollama_options")

        prompt = (
            f"Analyze this bug and provide:\n"
            f"1. root_cause: One concise root cause hypothesis\n"
            f"2. confidence: Your confidence (0.0-1.0)\n"
            f"3. evidence: Key evidence supporting your diagnosis\n\n"
            f"Problem: {str(ctx.op.problem_statement)[:2000]}\n"
            f"Repro: {str(getattr(ctx.op, 'repro_evidence', ''))[:1000]}"
        )
        try:
            client = OllamaLLMClient()
            response = client.generate(
                system_prompt="You are a diagnostic assistant. Analyze bugs concisely.",
                user_prompt=prompt,
                model=model,
                timeout=timeout,
                options=options,
            )
            import json, re
            match = re.search(r"\{.*\}", response or "", re.DOTALL)
            if match:
                parsed = json.loads(match.group(0))
                return {
                    "root_cause": str(parsed.get("root_cause", ""))[:500],
                    "confidence": float(parsed.get("confidence", 0.5)),
                    "evidence": str(parsed.get("evidence", ""))[:500],
                    "model": model,
                    "status": "success",
                }
            return {"root_cause": (response or "")[:500], "confidence": 0.3, "evidence": "", "model": model, "status": "parsed_failed"}
        except Exception as e:
            return {"root_cause": "", "confidence": 0.0, "evidence": "", "model": model, "status": f"error:{type(e).__name__}"}

    def diagnose_with_committee(self, ctx: HealContext) -> dict | None:
        """C6AD: Multi-model independent diagnosis → Borda selects best."""
        route_ctx = ctx.op.route_context if hasattr(ctx.op, "route_context") else {}
        signal_snapshot = route_ctx.get("signal_snapshot", {}) if isinstance(route_ctx, dict) else {}
        if not signal_snapshot.get("diagnosis_committee_enabled", False):
            return None

        diagnosis_models = signal_snapshot.get("diagnosis_models", [])
        if len(diagnosis_models) < 2:
            logger.warning("diagnosis_committee_enabled but <2 diagnosis_models, skipping")
            return None

        logger.info(f"--- [DIAGNOSIS COMMITTEE] k={len(diagnosis_models)} ---")
        diagnoses = []
        for model in diagnosis_models:
            result = self._invoke_diagnosis_model(model, ctx)
            diagnoses.append(result)
            logger.info(f"  📋 Diagnosis from {model}: status={result.get('status', 'unknown')} conf={result.get('confidence', 0)}")

        selected = _borda_select_diagnosis(diagnoses)
        if not selected or selected.get("status", "").startswith("error"):
            logger.warning("  ❌ All diagnosis models failed, falling back to single-model plan")
            return None

        ctx.op._committee_diagnosis = selected
        ctx.op._committee_diagnosis_trace = {
            "schema": DIAGNOSIS_COMMITTEE_SCHEMA,
            "enabled": True,
            "candidate_count": len(diagnoses),
            "diagnoses": diagnoses,
            "selected_model": selected.get("model", ""),
            "selected_root_cause": selected.get("root_cause", ""),
            "selected_confidence": selected.get("confidence", 0.0),
        }
        logger.info(f"  🏆 Diagnosis selected: model={selected['model']} conf={selected.get('confidence', 0)}")
        return selected

    def _invoke_audit_model(self, model: str, ctx: HealContext) -> dict:
        """Invoke a single model for audit/verification. Returns audit dict."""
        from nexus.services.local_heal.llm_client import OllamaLLMClient
        from nexus.engine.local_model_policy import LocalModelPolicy

        decision = LocalModelPolicy.select_model(
            task_type="swe_repair", phase="audit",
            context={"reasoning_mode": getattr(ctx.op, "reasoning_mode", "INTUITIVE")},
        )
        timeout = decision.get("timeout_seconds", 120)
        options = decision.get("ollama_options")

        patch_text = str(getattr(ctx.op, "final_patch", "") or "")[:2000]
        prompt = (
            f"Review this patch and determine if it correctly fixes the bug.\n"
            f"Output JSON with:\n"
            f"1. verdict: 'pass' or 'fail'\n"
            f"2. confidence: Your confidence (0.0-1.0)\n"
            f"3. reason: Brief explanation\n\n"
            f"Problem: {str(ctx.op.problem_statement)[:1500]}\n"
            f"Patch:\n{patch_text}"
        )
        try:
            client = OllamaLLMClient()
            response = client.generate(
                system_prompt="You are a code reviewer. Evaluate patches concisely.",
                user_prompt=prompt,
                model=model,
                timeout=timeout,
                options=options,
            )
            import json, re
            match = re.search(r"\{.*\}", response or "", re.DOTALL)
            if match:
                parsed = json.loads(match.group(0))
                verdict = str(parsed.get("verdict", "fail")).lower()
                return {
                    "verdict": "pass" if verdict == "pass" else "fail",
                    "confidence": float(parsed.get("confidence", 0.5)),
                    "reason": str(parsed.get("reason", ""))[:500],
                    "model": model,
                    "status": "success",
                }
            return {"verdict": "fail", "confidence": 0.3, "reason": (response or "")[:500], "model": model, "status": "parsed_failed"}
        except Exception as e:
            return {"verdict": "fail", "confidence": 0.0, "reason": "", "model": model, "status": f"error:{type(e).__name__}"}

    def audit_with_committee(self, ctx: HealContext) -> dict | None:
        """C6AE: Multi-model independent audit → Borda selects best."""
        route_ctx = ctx.op.route_context if hasattr(ctx.op, "route_context") else {}
        signal_snapshot = route_ctx.get("signal_snapshot", {}) if isinstance(route_ctx, dict) else {}
        if not signal_snapshot.get("audit_committee_enabled", False):
            return None

        audit_models = signal_snapshot.get("audit_models", [])
        if len(audit_models) < 2:
            logger.warning("audit_committee_enabled but <2 audit_models, skipping")
            return None

        logger.info(f"--- [AUDIT COMMITTEE] k={len(audit_models)} ---")
        audits = []
        for model in audit_models:
            result = self._invoke_audit_model(model, ctx)
            audits.append(result)
            logger.info(f"  🔍 Audit from {model}: verdict={result.get('verdict', 'unknown')} conf={result.get('confidence', 0)}")

        selected = _borda_select_diagnosis(audits)
        if not selected or selected.get("status", "").startswith("error"):
            logger.warning("  ❌ All audit models failed, keeping original verify result")
            return None

        ctx.op._committee_audit = selected
        ctx.op._committee_audit_trace = {
            "schema": "nexus.local_heal.committee_audit.v1",
            "enabled": True,
            "candidate_count": len(audits),
            "audits": audits,
            "selected_model": selected.get("model", ""),
            "selected_verdict": selected.get("verdict", ""),
            "selected_confidence": selected.get("confidence", 0.0),
        }

        if selected.get("verdict") == "pass":
            ctx.op.solve_eligible = True
            ctx.op.failure_reason = ""
            logger.info(f"  🏆 Audit PASSED: model={selected['model']} conf={selected.get('confidence', 0)}")
        else:
            ctx.op.solve_eligible = False
            ctx.op.failure_reason = f"COMMITTEE_AUDIT_REJECTION: {selected.get('reason', '')}"
            logger.info(f"  ❌ Audit FAILED: model={selected['model']} reason={selected.get('reason', '')}")

        return selected

    def run(self, ctx: HealContext) -> HealContext:
        route_ctx = ctx.op.route_context if hasattr(ctx.op, "route_context") else {}
        signal_snapshot = route_ctx.get("signal_snapshot", {}) if isinstance(route_ctx, dict) else {}
        
        use_committee = bool(signal_snapshot.get("local_committee_enabled", False) or signal_snapshot.get("use_committee", False))
        if not use_committee:
            return super().run(ctx)

        proposer_specs = signal_snapshot.get("proposer_specs")
        if proposer_specs is None:
            raise ValueError("Missing proposer_specs in signal_snapshot for local_committee_only")
        judge_model = signal_snapshot.get("judge_model")
        if not judge_model:
            raise ValueError("Missing judge_model in signal_snapshot for local_committee_only")
        proposer_specs = list(proposer_specs)
        if len(proposer_specs) < 2:
            raise ValueError("local_committee_only requires at least two proposer_specs")
        seen_models = set()
        for spec in proposer_specs:
            model_name = spec.get("model")
            role_name = spec.get("role")
            if not model_name:
                raise ValueError("Missing proposer spec model in signal_snapshot for local_committee_only")
            if not role_name:
                raise ValueError("Missing proposer spec role in signal_snapshot for local_committee_only")
            if model_name == judge_model:
                raise ValueError("judge_model must not also appear in proposer_specs")
            if model_name in seen_models:
                raise ValueError("Duplicate proposer model in signal_snapshot")
            seen_models.add(model_name)
            
        self.k = len(proposer_specs)
        logger.info(f"--- [COMMITTEE MODE ACTIVE] k={self.k} ---")
        
        # C6AD: D-phase committee diagnosis (before linear phases)
        self.diagnose_with_committee(ctx)
        
        # Phase 1-3: Linear Execution
        for phase in [self.repro_phase, self.plan_phase, self.loc_phase]:
            res = phase.execute(ctx)
            if not res.success:
                ctx.op.failure_reason = res.failure_reason
                return ctx

        # Phase 4: Committee Patch Search
        committee = CommitteeControllerV263(ctx.op.instance_id)
        committee.enabled = True # 強制啟用

        proposals = []
        candidate_snapshots = []
        previous_committee_model = getattr(ctx.op, "committee_proposer_model", None)
        previous_committee_role = getattr(ctx.op, "committee_proposer_role", None)
        for i, spec in enumerate(proposer_specs):
            logger.info(f"  🐝 Sampling candidate {i + 1}/{len(proposer_specs)}...")
            ctx.op.committee_proposer_model = spec["model"]
            ctx.op.committee_proposer_role = spec["role"]
            res = self.patch_phase.execute(ctx)
            if res.success:
                patch_text = str(getattr(ctx.op, "final_patch", "") or "")
                patch_decisions = [d for d in getattr(ctx.op, "model_decisions", []) if d.get("phase") == "patch"]
                model_decision = deepcopy(patch_decisions[-1]) if patch_decisions else {}
                invoked_model = str(model_decision.get("model", "") or "")
                if invoked_model != spec["model"]:
                    ctx.op.failure_reason = "COMMITTEE_PROPOSER_MODEL_MISMATCH"
                    ctx.op._committee_trace = {
                        "schema": COMMITTEE_ROUTE_SCHEMA,
                        "route_policy": COMMITTEE_ROUTE_POLICY,
                        "enabled": True,
                        "candidate_count": len(candidate_snapshots),
                        "proposer_candidates": candidate_snapshots,
                        "judge_selection": {
                            "winner_id": "",
                            "abstained": True,
                            "confidence": 0.0,
                            "verifier_gap": 0.0,
                            "failure_bucket": "model_mismatch",
                        },
                        "committee_receipt": {
                            "expected_model": spec["model"],
                            "invoked_model": invoked_model,
                        },
                    }
                    break
                patch_hash = _compute_patch_hash(patch_text)
                candidate_id = f"{ctx.op.instance_id}#candidate-{i + 1}"
                understanding = build_output_understanding_result(
                    candidate_id=candidate_id,
                    expected_model=spec["model"],
                    invoked_model=invoked_model,
                    target_file=str(getattr(ctx.op, "target_file", "") or ""),
                    target_symbol=str(getattr(ctx.op, "target_symbol", "") or ""),
                    patch_text=patch_text,
                    patch_hash=patch_hash,
                    model_decision=model_decision,
                )
                candidate_snapshot = {
                    "candidate_id": candidate_id,
                    "candidate_key": f"{ctx.op.instance_id}#proposer-{i + 1}",
                    "model": spec["model"],
                    "expected_model": spec["model"],
                    "invoked_model": invoked_model,
                    "role": spec["role"],
                    "attempt": i + 1,
                    "raw_label": str(model_decision.get("raw_label", "r:0,d:0,p:3,c:0") or "r:0,d:0,p:3,c:0"),
                    "patch_sha256": patch_hash,
                    "patch_length": len(patch_text),
                    "output_class": str(model_decision.get("output_class", "") or ""),
                    "parser_error_kind": str(model_decision.get("parser_error_kind", "") or ""),
                    "conversion_status": str(model_decision.get("conversion_status", "") or "none"),
                    "source_format": understanding.source_format,
                    "normalization_steps": list(understanding.normalization_steps),
                    "anchor_status": understanding.anchor_status,
                    "output_understanding": understanding.to_dict(),
                    "selected": False,
                    "applied": False,
                    "isolation_status": "stored",
                    "isolated_patch_sha256": patch_hash,
                    "isolated_patch_length": len(patch_text),
                    "isolation_store": "committee_trace",
                    "worktree_applied": False,
                    "model_decision": model_decision,
                }
                candidate_snapshots.append(candidate_snapshot)
                proposals.append({
                    "candidate_id": candidate_id,
                    "candidate_key": candidate_snapshot["candidate_key"],
                    "model": spec["model"],
                    "attempt": i + 1,
                    "raw_label": candidate_snapshot["raw_label"],
                    "artifacts": [patch_text],
                })
        if previous_committee_model is None:
            try:
                delattr(ctx.op, "committee_proposer_model")
            except AttributeError:
                pass
        else:
            ctx.op.committee_proposer_model = previous_committee_model
        if previous_committee_role is None:
            try:
                delattr(ctx.op, "committee_proposer_role")
            except AttributeError:
                pass
        else:
            ctx.op.committee_proposer_role = previous_committee_role

        if getattr(ctx.op, "failure_reason", "") == "COMMITTEE_PROPOSER_MODEL_MISMATCH":
            return ctx

        if not proposals:
            ctx.op.failure_reason = "COMMITTEE_COVERAGE_FAILURE"
            ctx.op._committee_trace = {
                "schema": COMMITTEE_ROUTE_SCHEMA,
                "route_policy": COMMITTEE_ROUTE_POLICY,
                "enabled": True,
                "candidate_count": 0,
                "proposer_candidates": [],
                "judge_selection": {
                    "winner_id": "",
                    "abstained": True,
                    "confidence": 0.0,
                    "verifier_gap": 0.0,
                    "failure_bucket": "coverage",
                },
                "committee_receipt": {},
            }
            return ctx

        # 執行委員會決議
        receipt = committee.process_proposals(proposals)

        # --- Candidate ID mapping: resolve winner_id → candidate_id ---
        winner_to_candidate_id = {p.get("candidate_id", ""): p.get("candidate_id", "") for p in proposals}
        winner_to_attempt = {}
        for p in proposals:
            model_prefix = f"{ctx.op.instance_id}-{p['model']}-{p['attempt']}-"
            winner_to_attempt[model_prefix] = p

        selected_candidate_id = ""
        candidate_id_mapping_mode = "missing"
        attempt_idx = -1
        selected_snapshot = {}

        if receipt.winner_id:
            # Try candidate_id mapping from proposals
            if receipt.winner_id in winner_to_candidate_id:
                selected_candidate_id = winner_to_candidate_id[receipt.winner_id]
                candidate_id_mapping_mode = "candidate_id"
                for idx, snap in enumerate(candidate_snapshots):
                    if snap.get("candidate_id") == selected_candidate_id:
                        attempt_idx = idx
                        selected_snapshot = snap
                        break
            else:
                # Legacy: match by winner_id prefix against proposal metadata
                for prefix, p in winner_to_attempt.items():
                    if receipt.winner_id.startswith(prefix):
                        attempt_idx = proposals.index(p)
                        selected_snapshot = candidate_snapshots[attempt_idx]
                        selected_candidate_id = selected_snapshot.get("candidate_id", "")
                        candidate_id_mapping_mode = "legacy_winner_id_prefix"
                        break

        judge_selection = {
            "winner_id": receipt.winner_id or "",
            "selected_candidate_id": selected_candidate_id,
            "candidate_id_mapping_mode": candidate_id_mapping_mode,
            "candidate_key": selected_snapshot.get("candidate_key", ""),
            "selected_model": selected_snapshot.get("model", ""),
            "selected_attempt": int(selected_snapshot.get("attempt", 0) or 0),
            "confidence": float(receipt.confidence or 0.0),
            "verifier_gap": float(receipt.verifier_gap or 0.0),
            "failure_bucket": receipt.failure_bucket or "",
            "abstained": bool(receipt.abstained),
        }
        ctx.op._committee_trace = {
            "schema": COMMITTEE_ROUTE_SCHEMA,
            "route_policy": COMMITTEE_ROUTE_POLICY,
            "enabled": True,
            "candidate_count": len(candidate_snapshots),
            "proposer_candidates": candidate_snapshots,
            "judge_selection": judge_selection,
            "committee_receipt": {
                "task_id": receipt.task_id,
                "k": receipt.k,
                "winner_id": receipt.winner_id or "",
                "selected_candidate_id": selected_candidate_id,
                "confidence": float(receipt.confidence or 0.0),
                "verifier_gap": float(receipt.verifier_gap or 0.0),
                "failure_bucket": receipt.failure_bucket or "",
                "abstain_reason": receipt.abstain_reason or "",
                "lane": receipt.lane,
                "policy_version": receipt.policy_version,
            },
        }

        # --- Mark selected candidate state on snapshot ---
        if selected_snapshot and selected_candidate_id:
            for snap in candidate_snapshots:
                if snap.get("candidate_id") == selected_candidate_id:
                    snap["selected"] = True
                    break

        if receipt.winner_id:
            if candidate_id_mapping_mode == "missing":
                ctx.op.final_patch = ""
                ctx.op.solve_eligible = False
                ctx.op.failure_reason = "COMMITTEE_WINNER_CANDIDATE_MAPPING_MISSING"
                ctx.op._committee_trace["judge_selection"]["failure_bucket"] = "candidate_mapping_missing"
                ctx.op._committee_trace["committee_receipt"]["selected_candidate_apply_supported"] = False
                ctx.op._committee_trace["committee_receipt"]["selected_candidate_applied"] = False
                ctx.op._committee_trace["committee_receipt"]["selected_candidate_patch_sha256"] = ""
                ctx.op._committee_trace["committee_receipt"]["applied_patch_sha256"] = ""
                ctx.op._committee_trace["committee_receipt"]["selected_candidate_apply_hash_match"] = False
                ctx.op._committee_trace["committee_receipt"]["selected_candidate_reapply_mode"] = "missing_mapping"
                return ctx

            # --- U3-3C: Unified apply for last and non-last candidates ---
            is_last_candidate = (attempt_idx == len(proposals) - 1)
            reapply_mode = "last_candidate_existing_path" if is_last_candidate else "non_last_candidate_reapplied"

            selected_patch = proposals[attempt_idx]["artifacts"][0] if attempt_idx >= 0 else ""

            if not selected_patch:
                ctx.op.final_patch = ""
                ctx.op.solve_eligible = False
                ctx.op.failure_reason = "COMMITTEE_SELECTED_CANDIDATE_ARTIFACT_MISSING"
                ctx.op._committee_trace["judge_selection"]["failure_bucket"] = "selected_candidate_artifact_missing"
                ctx.op._committee_trace["committee_receipt"]["selected_candidate_apply_supported"] = False
                ctx.op._committee_trace["committee_receipt"]["selected_candidate_applied"] = False
                ctx.op._committee_trace["committee_receipt"]["selected_candidate_patch_sha256"] = selected_snapshot.get("isolated_patch_sha256", "")
                ctx.op._committee_trace["committee_receipt"]["applied_patch_sha256"] = ""
                ctx.op._committee_trace["committee_receipt"]["selected_candidate_apply_hash_match"] = False
                ctx.op._committee_trace["committee_receipt"]["selected_candidate_reapply_mode"] = "missing_artifact"
                return ctx

            ctx.op._committee_trace["committee_receipt"]["selected_candidate_apply_supported"] = True
            ctx.op._committee_trace["committee_receipt"]["selected_candidate_applied"] = True
            ctx.op._committee_trace["committee_receipt"]["selected_candidate_reapply_mode"] = reapply_mode

            # Mark applied state on the selected candidate snapshot
            for snap in candidate_snapshots:
                if snap.get("candidate_id") == selected_candidate_id:
                    snap["applied"] = True
                    snap["worktree_applied"] = True
                    break

            ctx.op.final_patch = selected_patch

            # --- Hash verification ---
            selected_patch_hash = selected_snapshot.get("isolated_patch_sha256", "")
            applied_patch_hash = _compute_patch_hash(str(ctx.op.final_patch or ""))
            hash_match = bool(selected_patch_hash and applied_patch_hash and selected_patch_hash == applied_patch_hash)
            ctx.op._committee_trace["committee_receipt"]["selected_candidate_patch_sha256"] = selected_patch_hash
            ctx.op._committee_trace["committee_receipt"]["applied_patch_sha256"] = applied_patch_hash
            ctx.op._committee_trace["committee_receipt"]["selected_candidate_apply_hash_match"] = hash_match

            if not hash_match:
                ctx.op.final_patch = ""
                ctx.op.solve_eligible = False
                ctx.op.failure_reason = "COMMITTEE_SELECTED_CANDIDATE_APPLY_HASH_MISMATCH"
                ctx.op._committee_trace["judge_selection"]["failure_bucket"] = "candidate_apply_hash_mismatch"
                ctx.op._committee_trace["committee_receipt"]["selected_candidate_reapply_mode"] = "hash_mismatch"
                logger.warning(f"  ❌ Hash mismatch: selected={selected_patch_hash} applied={applied_patch_hash}")
                return ctx

            logger.info(f"  🏆 Winner Selected: {receipt.winner_id} (candidate_id={selected_candidate_id}, mode={reapply_mode})")

            # Phase 5: Final Verification
            verify_res = self.verify_phase.execute(ctx)
            if verify_res.success:
                ctx.op.solve_eligible = True
            else:
                ctx.op.failure_reason = f"VERIFIER_REJECTION:{verify_res.failure_reason}"

            # Project verifier evidence truth into committee receipt
            verifier_evidence_passed = bool(getattr(ctx.op, "_orchestrator_verifier_evidence_passed", False))
            verifier_evidence_fields = str(getattr(ctx.op, "_orchestrator_verifier_evidence_fields", "") or "")
            ctx.op._committee_trace["committee_receipt"]["verifier_evidence_passed"] = verifier_evidence_passed
            ctx.op._committee_trace["committee_receipt"]["verifier_evidence_fields"] = verifier_evidence_fields
            ctx.op._committee_trace["committee_receipt"]["verifier_rejection_reason"] = str(verify_res.failure_reason if not verify_res.success else "")

            # C6AE: A-phase committee audit (after verify)
            self.audit_with_committee(ctx)
        else:
            ctx.op.failure_reason = "COMMITTEE_SELECTION_FAILURE"

        return ctx
