from pathlib import Path
from typing import Any
from nexus.services.local_heal.interface import IPhase, PhaseResult
from nexus.services.local_heal.reproduction import ReproductionRunner
from nexus.services.local_heal.context import HealContext

class ReproductionPhase(IPhase):
    """Phase 1: Reproduction (建立物理證據)"""
    def __init__(self, repro_runner: ReproductionRunner):
        self.repro_runner = repro_runner

    def execute(self, ctx: HealContext) -> PhaseResult:
        if ctx.op.repro_evidence:
            ctx.op.reproduced = True
            return PhaseResult(success=True)

        if not ctx.op.repro_script:
            # Note: Generating script logic remains in pipeline for now or passed as a helper
            return PhaseResult(success=False, exit_layer="repro_runner", error_reason="NO_REPRO_SCRIPT")

        success, evidence = self.repro_runner.run_repro(ctx.op.repro_script)
        ctx.op.repro_evidence = evidence
        ctx.op.reproduced = bool(success)

        if not success or not evidence or len(evidence.strip()) < 10:
            if self.repro_runner.is_environment_failure(evidence):
                reason = "REPRO_ENVIRONMENT_FAILURE"
            elif not success:
                reason = "REPRO_NOT_REPRODUCED"
            else:
                reason = "REPRO_EVIDENCE_TOO_SHORT"
            return PhaseResult(success=False, exit_layer="repro_runner", error_reason=reason)

        return PhaseResult(success=True)
