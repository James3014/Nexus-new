import os
from typing import Any, Dict
from nexus.services.local_heal.interface import IPhase, PhaseResult, PlanningInput, PlanningOutput, RepairPlan
from nexus.services.local_heal.planner import Planner
from nexus.services.local_heal.context import HealContext
from nexus.engine.local_model_policy import LocalModelPolicy
from nexus.services.local_heal.model_result import classify_model_exception
from nexus.services.local_heal.reasoning_router import ReasoningRouter
from nexus.services.local_heal.llm_client import ILLMClient
from nexus.services.local_heal.planner import DeterministicSymbolExtractor
from nexus.engine.local_model_policy import SidecarConfig

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
            repair_plan = self.planner.create_plan(
                input_data.problem_statement,
                input_data.repro_evidence,
                model_name=plan_decision["model"],
                timeout_seconds=plan_decision["timeout_seconds"],
                options=plan_decision.get("ollama_options"),
            )
            return PlanningOutput(
                success=True,
                plan=repair_plan,
                model_decision=plan_decision
            )
        except Exception as exc:
            reason = classify_model_exception(exc)
            return PlanningOutput(
                success=False,
                plan=None,
                model_decision=plan_decision,
                error_reason=reason
            )

    def execute(self, ctx: HealContext) -> PhaseResult:
        if not ctx.op.reproduced or not ctx.op.repro_evidence:
            return PhaseResult(success=False, failure_reason="PREREQUISITE_FAILED_REPRO")

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

        # 3. 呼叫解耦執行 — FAST mode if router says so OR env var set
        use_fast = reasoning_mode == "FAST" or os.environ.get("NEXUS_FAST_MODE") == "1"
        if use_fast:
            det_symbols = DeterministicSymbolExtractor.extract(input_data.problem_statement, input_data.repro_evidence)
            output = PlanningOutput(
                success=True,
                plan=RepairPlan(
                    search_symbols=det_symbols, 
                    repair_strategy="FAST_MODE: Deterministic extraction", 
                    violated_invariants=[]
                ),
                model_decision={"phase": "planning", "model": "deterministic", "reasoning_mode": "FAST"}
            )
        else:
            output = self.run(input_data)
        
        # 覆蓋回 model_decisions
        ctx.op.model_decisions[-1] = {"phase": "planning", **output.model_decision}

        # 4. 寫回狀態
        if not output.success:
            ctx.op.failure_reason = output.failure_reason
            self._record_model_status(ctx, output.failure_reason, detail=output.failure_reason, phase="planning")
            return PhaseResult(success=False, exit_layer="planning", failure_reason=output.failure_reason)

        ctx.op.plan = self._apply_route_hints(ctx, output.plan)

        # 5. Gemma sidecar (shadow lane, no authority)
        ctx._sidecar_enabled = SidecarConfig.SIDECAR_ENABLED
        ctx._sidecar_model = SidecarConfig.SIDECAR_MODEL if SidecarConfig.SIDECAR_ENABLED else ""
        ctx._sidecar_contributed = False
        
        if SidecarConfig.SIDECAR_ENABLED and self.planner.llm_client:
            try:
                sidecar_prompt = (
                    f"Analyze this bug and provide:\n"
                    f"1. Root cause hypothesis\n"
                    f"2. Candidate files to modify\n"
                    f"3. Minimal fix strategy\n\n"
                    f"Problem: {input_data.problem_statement[:1000]}\n"
                    f"Repro evidence: {input_data.repro_evidence[:500]}"
                )
                sidecar_response = self.planner.llm_client.generate(
                    system_prompt="You are a diagnostic assistant. Analyze the bug and propose a fix strategy.",
                    user_prompt=sidecar_prompt,
                    model=SidecarConfig.SIDECAR_MODEL,
                    timeout=120,
                    options=SidecarConfig.get_sidecar_options(),
                )
                if sidecar_response:
                    ctx._sidecar_contributed = True
                    ctx.op.model_decisions.append({
                        "phase": "planning_sidecar",
                        "model": SidecarConfig.SIDECAR_MODEL,
                        "status": "SUCCESS",
                        "detail": sidecar_response[:500],
                    })
            except Exception:
                pass  # Sidecar failure is non-blocking
        return PhaseResult(success=True)

    @staticmethod
    def _apply_route_hints(ctx: HealContext, plan: RepairPlan) -> RepairPlan:
        route_ctx = ctx.op.route_context if isinstance(ctx.op.route_context, dict) else {}
        target_symbol = str(route_ctx.get("target_symbol", "") or "").strip()
        if not target_symbol:
            return plan

        existing = [s for s in (plan.search_symbols or []) if isinstance(s, str) and s.strip()]
        merged = [target_symbol] + [s for s in existing if s != target_symbol]
        return RepairPlan(
            search_symbols=merged,
            repair_strategy=plan.repair_strategy,
            violated_invariants=plan.violated_invariants,
        )

    def _record_model_status(self, ctx: HealContext, status: str, detail: str = "", *, phase: str | None = None) -> None:
        for decision in reversed(ctx.op.model_decisions):
            if phase is None or decision.get("phase") == phase:
                decision["status"] = status
                if detail:
                    decision["detail"] = detail[:500]
                return
