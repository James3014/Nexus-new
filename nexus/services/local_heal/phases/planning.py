from typing import Any
from nexus.services.local_heal.interface import IPhase, PhaseResult
from nexus.services.local_heal.planner import Planner
from nexus.services.local_heal.context import HealContext

class PlanningPhase(IPhase):
    """Phase 2: Planning (戰略規劃)"""
    def __init__(self, planner: Planner):
        self.planner = planner

    def execute(self, ctx: HealContext) -> PhaseResult:
        if not ctx.op.reproduced or not ctx.op.repro_evidence:
            return PhaseResult(success=False, error_reason="PREREQUISITE_FAILED_REPRO")

        # 這裡未來可以帶入模型選擇邏輯，目前保持簡單
        try:
            # Note: Model selection is still handled by caller or passed in
            # For decoupling, we assume the planner is already configured
            ctx.op.plan = self.planner.create_plan(
                ctx.op.problem_statement,
                ctx.op.repro_evidence
            )
            
            # Algebraic Reasoning Mode Detection
            if "astropy" in ctx.op.problem_statement.lower() or "astropy" in str(ctx.op.repo_dir).lower():
                ctx.op.reasoning_mode = "ALGEBRAIC"
            else:
                ctx.op.reasoning_mode = "INTUITIVE"
                
            return PhaseResult(success=True)
        except Exception as exc:
            return PhaseResult(success=False, exit_layer="planning", error_reason=f"PLANNING_EXCEPTION:{str(exc)}")
