from typing import Any, Callable, List
from nexus.services.local_heal.interface import IPhase, PhaseResult
from nexus.services.local_heal.context import HealContext
from nexus.services.local_heal.governance_gate import GovernanceGate

class HealOrchestrator:
    """🛡️ Nexus Heal Orchestrator (Modular / Strategy-Driven)"""
    
    def __init__(
        self,
        phases: List[IPhase],
        governance_gate: GovernanceGate,
        receipt_writer: Callable[[HealContext], Any] | None = None,
    ):
        self.phases = phases
        self.governance_gate = governance_gate
        self.receipt_writer = receipt_writer

    def run(self, ctx: HealContext) -> HealContext:
        """
        執行多階段修復管線。
        """
        for phase in self.phases:
            try:
                result = phase.execute(ctx)
            except Exception as exc:
                ctx.gov.gate_exit = phase.__class__.__name__
                ctx.op.failure_reason = f"{type(exc).__name__}:{exc}"
                break
            
            if not result.success:
                ctx.gov.gate_exit = result.exit_layer or "unknown"
                ctx.op.failure_reason = result.error_reason
                break
        else:
            # 如果全部成功
            ctx.gov.gate_exit = "verification"
            
        ctx.op.runner_completed = True
        # 執行審計
        self.governance_gate.audit(ctx)

        if self.receipt_writer:
            ctx.op.receipt_path = str(self.receipt_writer(ctx))
        
        return ctx
