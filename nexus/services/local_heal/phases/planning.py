from typing import Any, Dict
from nexus.services.local_heal.interface import IPhase, PhaseResult, PlanningInput, PlanningOutput
from nexus.services.local_heal.planner import Planner
from nexus.services.local_heal.context import HealContext
from nexus.engine.local_model_policy import LocalModelPolicy
from nexus.services.local_heal.model_result import classify_model_exception
from nexus.services.local_heal.reasoning_router import ReasoningRouter
from nexus.services.local_heal.llm_client import ILLMClient

class PlanningPhase(IPhase):
    """Phase 2: Planning (戰略規劃)"""
    def __init__(self, planner: Planner, router: ReasoningRouter | None = None, llm_client: ILLMClient | None = None):
        self.planner = planner
        self.router = router or ReasoningRouter()
        if llm_client:
            self.planner.llm_client = llm_client

    def run(self, input_data: PlanningInput) -> PlanningOutput:
        """Stateless TDD-ready execution logic."""
        # 選擇模型與參數
        plan_decision = LocalModelPolicy.select_model(
            task_type="swe_repair", 
            phase="planning", 
            context={"reasoning_mode": input_data.reasoning_mode}
        )

        try:
            plan = self.planner.create_plan(
                input_data.problem_statement,
                input_data.repro_evidence,
                model_name=plan_decision["model"],
                timeout_seconds=plan_decision["timeout_seconds"],
                options=plan_decision.get("ollama_options"),
            )
            return PlanningOutput(
                success=True,
                plan=plan,
                model_decision=plan_decision
            )
        except Exception as exc:
            reason = classify_model_exception(exc)
            return PlanningOutput(
                success=False,
                plan={},
                model_decision=plan_decision,
                error_reason=reason
            )

    def execute(self, ctx: HealContext) -> PhaseResult:
        if not ctx.op.reproduced or not ctx.op.repro_evidence:
            return PhaseResult(success=False, error_reason="PREREQUISITE_FAILED_REPRO")

        # 1. 決定 reasoning mode (委託 ReasoningRouter)
        reasoning_mode = self.router.route(ctx.op.problem_statement, ctx.op.repo_dir)
        ctx.op.reasoning_mode = reasoning_mode

        # 2. 構建輸入
        input_data = PlanningInput(
            problem_statement=ctx.op.problem_statement,
            repro_evidence=ctx.op.repro_evidence,
            repo_dir=ctx.op.repo_dir,
            reasoning_mode=reasoning_mode
        )

        ctx.op.model_decisions.append({"phase": "planning", "model": "qwen2.5-coder:7b"})  # Placeholder decision

        # 3. 呼叫解耦執行
        output = self.run(input_data)
        
        # 覆蓋回 model_decisions
        ctx.op.model_decisions[-1] = {"phase": "planning", **output.model_decision}

        # 4. 寫回狀態
        if not output.success:
            ctx.op.failure_reason = output.error_reason
            self._record_model_status(ctx, output.error_reason, detail=output.error_reason, phase="planning")
            return PhaseResult(success=False, exit_layer="planning", error_reason=output.error_reason)

        ctx.op.plan = output.plan
        return PhaseResult(success=True)

    def _record_model_status(self, ctx: HealContext, status: str, detail: str = "", *, phase: str | None = None) -> None:
        for decision in reversed(ctx.op.model_decisions):
            if phase is None or decision.get("phase") == phase:
                decision["status"] = status
                if detail:
                    decision["detail"] = detail[:500]
                return
