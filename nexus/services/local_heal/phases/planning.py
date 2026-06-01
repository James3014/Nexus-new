from typing import Any, Dict
from nexus.services.local_heal.interface import IPhase, PhaseResult
from nexus.services.local_heal.planner import Planner
from nexus.services.local_heal.context import HealContext
from nexus.engine.local_model_policy import LocalModelPolicy
from nexus.services.local_heal.model_result import classify_model_exception

class PlanningPhase(IPhase):
    """Phase 2: Planning (戰略規劃)"""
    def __init__(self, planner: Planner):
        self.planner = planner

    def execute(self, ctx: HealContext) -> PhaseResult:
        if not ctx.op.reproduced or not ctx.op.repro_evidence:
            return PhaseResult(success=False, error_reason="PREREQUISITE_FAILED_REPRO")

        # 代數推理模式判定
        if "astropy" in ctx.op.problem_statement.lower() or "astropy" in str(ctx.op.repo_dir).lower():
            ctx.op.reasoning_mode = "ALGEBRAIC"
        else:
            ctx.op.reasoning_mode = "INTUITIVE"

        # 選擇模型與參數
        plan_decision = LocalModelPolicy.select_model(
            task_type="swe_repair", 
            phase="planning", 
            context={"reasoning_mode": ctx.op.reasoning_mode}
        )
        ctx.op.model_decisions.append({"phase": "planning", **plan_decision})

        try:
            ctx.op.plan = self.planner.create_plan(
                ctx.op.problem_statement,
                ctx.op.repro_evidence,
                model_name=plan_decision["model"],
                timeout_seconds=plan_decision["timeout_seconds"],
            )
            return PhaseResult(success=True)
        except Exception as exc:
            reason = classify_model_exception(exc)
            ctx.op.failure_reason = reason
            self._record_model_status(ctx, reason, detail=f"{type(exc).__name__}: {exc}", phase="planning")
            return PhaseResult(success=False, exit_layer="planning", error_reason=f"PLANNING_EXCEPTION:{str(exc)}" if reason != "MODEL_TIMEOUT" else "MODEL_TIMEOUT")

    def _record_model_status(self, ctx: HealContext, status: str, detail: str = "", *, phase: str | None = None) -> None:
        for decision in reversed(ctx.op.model_decisions):
            if phase is None or decision.get("phase") == phase:
                decision["status"] = status
                if detail:
                    decision["detail"] = detail[:500]
                return
