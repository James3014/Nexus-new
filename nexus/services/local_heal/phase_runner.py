from typing import Tuple
from nexus.services.local_heal.interface import IPhase, PhaseResult
from nexus.services.local_heal.context import HealContext
from nexus.services.local_heal.latency_ledger import LatencyLedger

class PhaseRunner:
    """🛡️ Phase Runner: Encapsulates the execution logic of a single pipeline phase."""

    def run_phase(self, phase: IPhase, phase_name: str, ctx: HealContext, ledger: LatencyLedger) -> PhaseResult:
        pt = ledger.start_phase(phase_name)
        try:
            res = phase.execute(ctx)
            if res.success:
                ledger.end_phase(pt, success=True)
            else:
                ledger.end_phase(pt, success=False, error=res.failure_reason[:200])
            from nexus.services.local_heal.world_c_receipt import record_world_c_phase_result

            record_world_c_phase_result(ctx, phase_name, res)
            return res
        except Exception as exc:
            import traceback
            error_msg = f"{type(exc).__name__}:{exc}"
            ledger.end_phase(pt, success=False, error=error_msg[:200])
            result = PhaseResult(
                success=False, 
                exit_layer=phase.__class__.__name__, 
                failure_reason=error_msg,
                error_metadata={"traceback": traceback.format_exc()}
            )
            from nexus.services.local_heal.world_c_receipt import record_world_c_phase_result

            record_world_c_phase_result(ctx, phase_name, result)
            return result
