from typing import Any
from nexus.services.local_heal.interface import IPhase, PhaseResult
from nexus.services.local_heal.evaluation_gate import EvaluationGate
from nexus.services.local_heal.context import HealContext
from pathlib import Path
import os

class VerificationPhase(IPhase):
    """Phase 5: Verification (代數驗證)"""
    def __init__(self, eval_gate: EvaluationGate, hidden_required: bool = False):
        self.eval_gate = eval_gate
        self.hidden_required = hidden_required

    def execute(self, ctx: HealContext) -> PhaseResult:
        if not ctx.op.final_patch:
            return PhaseResult(success=False, error_reason="NO_PATCH_TO_VERIFY")

        repro_path = ctx.op.repo_dir / "reproduce_bug.py"
        repro_path.write_text(ctx.op.repro_script, encoding="utf-8")

        try:
            verification_python = ctx.op.python_executable or "python3"
            visible_results = self.eval_gate.run_visible_tests([[verification_python, "reproduce_bug.py"]])
            hidden_results = []
            if self.hidden_required:
                hidden_results = self.eval_gate.run_hidden_verifier([])

            ctx.op.hidden_verifier_passed = all(r.passed for r in visible_results + hidden_results)
            ctx.op.evaluation_report = self.eval_gate.get_redacted_report(visible_results, hidden_results)

            if ctx.op.hidden_verifier_passed:
                ctx.op.solve_eligible = True
                return PhaseResult(success=True)
            else:
                ctx.op.solve_eligible = False
                return PhaseResult(success=False, exit_layer="verification", error_reason="VERIFICATION_FAILED")
        finally:
            if repro_path.exists():
                try: os.remove(repro_path)
                except OSError: pass
