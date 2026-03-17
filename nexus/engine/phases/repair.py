#!/usr/bin/env python3
from typing import Any, Dict
from nexus.engine.phases.base import BasePhaseHandler
from nexus.core.state_contracts import NexusState
from nexus.services.reviewer import CodexLoopV2


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
        skill_id = candidates[0]["skill_id"] if candidates else "default-repair"

        audit_level = context.get("audit_level", "standard")

        if self.orchestrator_factory:
            engine_loop = self.orchestrator_factory(
                mode="agent-shield",
                scope="staged",
                apply_patch=not dry_run,
                task=task,
                skill_id=skill_id,
                audit_level=audit_level,
            )
        else:
            # Legacy fallback if no factory provided
            engine_loop = CodexLoopV2(
                mode="agent-shield",
                scope="staged",
                apply_patch=not dry_run,
                task=task,
                skill_id=skill_id,
                audit_level=audit_level,
            )

        res_obj = engine_loop.run_review()
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
