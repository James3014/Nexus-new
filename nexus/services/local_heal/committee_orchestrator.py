from typing import Any, Callable, List, Dict
from copy import deepcopy
import hashlib
import logging
import os
import time
from nexus.services.local_heal.interface import IPhase, PhaseResult
from nexus.services.local_heal.context import HealContext
from nexus.services.local_heal.orchestrator import HealOrchestrator
from nexus.committee.controller import CommitteeControllerV263

COMMITTEE_ROUTE_SCHEMA = "nexus.local_heal.committee_trace.v1"
COMMITTEE_ROUTE_POLICY = "qwen_3b_judge_plus_qwen_7b_plus_deepseek_6_7b"
COMMITTEE_PROPOSER_SPECS = (
    {"model": "qwen2.5-coder:7b-instruct", "role": "primary"},
    {"model": "deepseek-coder:6.7b-instruct", "role": "secondary"},
)

logger = logging.getLogger(__name__)

class CommitteeOrchestrator(HealOrchestrator):
    """
    🤝 Nexus Committee Orchestrator (v26)
    實施 Verifier-backed Committee Search。
    在 Patch Synthesis 階段進行多樣本採樣與 Borda 選優。
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.k = len(COMMITTEE_PROPOSER_SPECS)

    def run(self, ctx: HealContext) -> HealContext:
        if os.getenv("NEXUS_USE_COMMITTEE", "0") != "1":
            return super().run(ctx)

        logger.info(f"--- [COMMITTEE MODE ACTIVE] k={self.k} ---")
        
        # Phase 1-3: Linear Execution
        for phase in [self.repro_phase, self.plan_phase, self.loc_phase]:
            res = phase.execute(ctx)
            if not res.success:
                ctx.op.failure_reason = res.failure_reason
                return ctx

        # Phase 4: Committee Patch Search
        committee = CommitteeControllerV263(ctx.op.instance_id)
        committee.enabled = True # 強制啟用

        proposer_specs = list(COMMITTEE_PROPOSER_SPECS[: self.k])
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
                model_decision = deepcopy(ctx.op.model_decisions[-1]) if getattr(ctx.op, "model_decisions", None) else {}
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
                candidate_id = f"{ctx.op.instance_id}#candidate-{i + 1}"
                candidate_snapshot = {
                    "candidate_id": candidate_id,
                    "candidate_key": f"{ctx.op.instance_id}#proposer-{i + 1}",
                    "model": spec["model"],
                    "role": spec["role"],
                    "attempt": i + 1,
                    "raw_label": str(model_decision.get("raw_label", "r:0,d:0,p:3,c:0") or "r:0,d:0,p:3,c:0"),
                    "patch_sha256": hashlib.sha256(patch_text.encode("utf-8")).hexdigest()[:16] if patch_text else "",
                    "patch_length": len(patch_text),
                    "selected": False,
                    "applied": False,
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

        if receipt.winner_id:
            if candidate_id_mapping_mode == "missing":
                ctx.op.final_patch = ""
                ctx.op.solve_eligible = False
                ctx.op.failure_reason = "COMMITTEE_WINNER_CANDIDATE_MAPPING_MISSING"
                ctx.op._committee_trace["judge_selection"]["failure_bucket"] = "candidate_mapping_missing"
                ctx.op._committee_trace["committee_receipt"]["selected_candidate_apply_supported"] = False
                return ctx

            if attempt_idx != len(proposals) - 1:
                ctx.op.final_patch = ""
                ctx.op.solve_eligible = False
                ctx.op.failure_reason = "COMMITTEE_SELECTED_NON_APPLIED_CANDIDATE_UNSUPPORTED"
                ctx.op._committee_trace["judge_selection"]["failure_bucket"] = "selected_candidate_not_applied"
                ctx.op._committee_trace["committee_receipt"]["selected_candidate_apply_supported"] = False
                return ctx
            ctx.op._committee_trace["committee_receipt"]["selected_candidate_apply_supported"] = True
            ctx.op.final_patch = proposals[attempt_idx]["artifacts"][0]
            logger.info(f"  🏆 Winner Selected: {receipt.winner_id} (candidate_id={selected_candidate_id})")

            # Phase 5: Final Verification
            verify_res = self.verify_phase.execute(ctx)
            if verify_res.success:
                ctx.op.solve_eligible = True
            else:
                ctx.op.failure_reason = f"VERIFIER_REJECTION:{verify_res.failure_reason}"
        else:
            ctx.op.failure_reason = "COMMITTEE_SELECTION_FAILURE"

        return ctx
