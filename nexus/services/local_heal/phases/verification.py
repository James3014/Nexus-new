from typing import Any
from nexus.services.local_heal.interface import IPhase, PhaseResult, VerificationInput, VerificationOutput
from nexus.services.local_heal.evaluation_gate import EvaluationGate
from nexus.services.local_heal.context import HealContext
from pathlib import Path
import os

class VerificationPhase(IPhase):
    """Phase 5: Verification (代數驗證)"""
    def __init__(self, eval_gate: EvaluationGate, hidden_required: bool = False):
        self.eval_gate = eval_gate
        self.hidden_required = hidden_required

    def run(self, input_data: VerificationInput) -> VerificationOutput:
        """Stateless TDD-ready execution logic."""
        if not input_data.final_patch:
            return VerificationOutput(
                success=False,
                evaluation_report="",
                hidden_verifier_passed=False,
                solve_eligible=False,
                error_reason="NO_PATCH_TO_VERIFY"
            )

        repro_path = input_data.repo_dir / "reproduce_bug.py"
        repro_path.write_text(input_data.repro_script, encoding="utf-8")

        try:
            verification_python = input_data.python_executable or "python3"
            visible_results = self.eval_gate.run_visible_tests([[verification_python, "reproduce_bug.py"]])
            hidden_results = []
            if self.hidden_required:
                hidden_results = self.eval_gate.run_hidden_verifier([])

            passed = all(r.passed for r in visible_results + hidden_results)
            report = self.eval_gate.get_redacted_report(visible_results, hidden_results)

            if passed:
                return VerificationOutput(
                    success=True,
                    evaluation_report=report,
                    hidden_verifier_passed=True,
                    solve_eligible=True
                )
            else:
                return VerificationOutput(
                    success=False,
                    evaluation_report=report,
                    hidden_verifier_passed=False,
                    solve_eligible=False,
                    error_reason="VERIFICATION_FAILED"
                )
        finally:
            if repro_path.exists():
                try:
                    os.remove(repro_path)
                except OSError:
                    pass

    def execute(self, ctx: HealContext) -> PhaseResult:
        input_data = VerificationInput(
            instance_id=ctx.op.instance_id,
            repo_dir=ctx.op.repo_dir,
            problem_statement=ctx.op.problem_statement,
            final_patch=ctx.op.final_patch,
            repro_script=ctx.op.repro_script,
            python_executable=ctx.op.python_executable
        )

        output = self.run(input_data)
        
        ctx.op.evaluation_report = output.evaluation_report
        ctx.op.hidden_verifier_passed = output.hidden_verifier_passed
        ctx.op.solve_eligible = output.solve_eligible
        
        if not output.success:
            ctx.op.failure_reason = output.failure_reason
            return PhaseResult(success=False, exit_layer="verification", failure_reason=output.failure_reason)

        ctx.op.failure_reason = ""
        return PhaseResult(success=True)
