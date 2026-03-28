#!/usr/bin/env python3
from typing import Any, Dict
from nexus.engine.phases.base import BasePhaseHandler
from nexus.core.state_contracts import NexusState
from nexus.engine.phases.local_repair import try_local_repair
from nexus.services.reviewer import GatewayReviewLoop


class RepairPhaseHandler(BasePhaseHandler):
    """
    🛠️ Phase R: Repair & Verification
    封裝核心修復循環與 Audit 對接。
    """

    def __init__(
        self,
        project_root: Any,
        run_dir: Any,
        router: Any = None,
        orchestrator_factory: Any = None,
    ):
        super().__init__(project_root, run_dir)
        self.router = router
        self.orchestrator_factory = orchestrator_factory

    def run(self, state: NexusState, context: Dict[str, Any]) -> Dict[str, Any]:
        task = context.get("task")
        diag_pack = context.get("diag_pack")
        repair_attempts = context.get("attempt", 1)
        dry_run = context.get("dry_run", False)

        print(f"🛠️ [R-Stage] Repair Attempt {repair_attempts}")

        candidates = self.router.route_candidates("R", diag_pack)
        selected = candidates[0] if candidates else {}
        skill_id = selected.get("skill_id", "default-repair")
        decision_id = selected.get("decision_id", f"dec_r_internal_{state.task_id}")
        phase_decisions = dict(state.metadata.get("phase_decisions", {}) or {})
        phase_skills = dict(state.metadata.get("phase_skills", {}) or {})
        phase_decisions["R"] = decision_id
        phase_skills["R"] = skill_id
        state.metadata["phase_decisions"] = phase_decisions
        state.metadata["phase_skills"] = phase_skills

        audit_level = context.get("audit_level", "standard")

        local_result = try_local_repair(
            project_root=self.project_root,
            state=state,
            context={"task": task, **context},
        )
        if local_result is not None:
            return local_result
        if state.metadata.get("benchmark_run"):
            return {
                "status": "REJECTED",
                "result_object": {
                    "status": "REJECTED",
                    "summary": "Benchmark repair path requires deterministic local repair and will not use external review.",
                    "violations": [],
                    "patch_generated": False,
                    "patch_apply_success": False,
                    "no_change_reason": "benchmark_requires_local_repair",
                    "audit_metadata": {"repair_strategy": "internal_only"},
                },
                "tokens_used": 0,
                "token_raw_model": 0,
                "token_fallback_est": 0,
                "token_capture_status": "internal",
            }

        if self.orchestrator_factory:
            engine_loop = self.orchestrator_factory(
                mode="agent-shield",
                scope="all",
                apply_patch=not dry_run,
                task=task,
                skill_id=skill_id,
                audit_level=audit_level,
            )
        else:
            # Legacy fallback if no factory provided
            engine_loop = GatewayReviewLoop(
                mode="agent-shield",
                scope="all",
                apply_patch=not dry_run,
                task=task,
                skill_id=skill_id,
                audit_level=audit_level,
            )

        res_obj = engine_loop.run_review()
        if isinstance(res_obj, dict):
            res_obj["decision_id"] = decision_id
            res_obj["skill_id"] = skill_id
        return {
            "status": res_obj.get("status", "REJECTED"),
            "result_object": res_obj,
            "tokens_used": engine_loop.total_tokens,
            "token_raw_model": engine_loop.total_raw_model,
            "token_fallback_est": engine_loop.total_fallback_est,
            "token_capture_status": "|".join(engine_loop.token_capture_statuses)
            if hasattr(engine_loop, "token_capture_statuses")
            else "unknown",
        }
