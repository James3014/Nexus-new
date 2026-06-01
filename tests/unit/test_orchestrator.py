import pytest
from pathlib import Path
from unittest.mock import MagicMock
from nexus.services.local_heal.context import HealContext, OperationalContext, GovernanceContext
from nexus.services.local_heal.interface import IPhase, PhaseResult
from nexus.services.local_heal.governance_gate import GovernanceGate
from nexus.services.local_heal.orchestrator import HealOrchestrator
from nexus.services.local_heal.evaluation_gate import EvaluationGate
from nexus.services.local_heal.parser import SearchReplaceParser
from nexus.services.local_heal.patcher import Patcher
from nexus.services.local_heal.phases.patch_synthesis import PatchSynthesisPhase
from nexus.services.local_heal.phases.verification import VerificationPhase

def test_orchestrator_flow():
    op = OperationalContext(instance_id="t1", repo_dir=Path("/tmp"), problem_statement="p")
    gov = GovernanceContext()
    ctx = HealContext(op=op, gov=gov)
    
    p1 = MagicMock(spec=IPhase)
    p1.execute.return_value = PhaseResult(success=True)
    
    p2 = MagicMock(spec=IPhase)
    p2.execute.return_value = PhaseResult(success=False, exit_layer="test_layer", error_reason="TEST_FAIL")
    
    gate = MagicMock(spec=GovernanceGate)
    
    orch = HealOrchestrator(phases=[p1, p2], governance_gate=gate)
    res_ctx = orch.run(ctx)
    
    assert res_ctx.gov.gate_exit == "test_layer"
    assert res_ctx.op.failure_reason == "TEST_FAIL"
    gate.audit.assert_called_once_with(res_ctx)


def test_orchestrator_contains_phase_exception_and_writes_receipt(tmp_path):
    op = OperationalContext(instance_id="t2", repo_dir=tmp_path, problem_statement="p")
    gov = GovernanceContext()
    ctx = HealContext(op=op, gov=gov)

    class ExplodingPhase(IPhase):
        def execute(self, ctx):
            raise TimeoutError("phase timed out")

    receipt_calls = []

    def receipt_writer(ctx):
        receipt_calls.append(ctx)
        receipt_path = tmp_path / "receipt.json"
        receipt_path.write_text('{"ok": true}\n', encoding="utf-8")
        return receipt_path

    gate = MagicMock(spec=GovernanceGate)
    orch = HealOrchestrator(
        phases=[ExplodingPhase()],
        governance_gate=gate,
        receipt_writer=receipt_writer,
    )

    res_ctx = orch.run(ctx)

    assert res_ctx.op.runner_completed is True
    assert res_ctx.gov.gate_exit == "ExplodingPhase"
    assert res_ctx.op.failure_reason == "TimeoutError:phase timed out"
    assert res_ctx.op.receipt_path == str(tmp_path / "receipt.json")
    assert receipt_calls == [res_ctx]
    gate.audit.assert_called_once_with(res_ctx)


def test_orchestrator_runs_patch_and_verification_phases(tmp_path):
    target = tmp_path / "hello.py"
    target.write_text("def hello():\n    return False\n", encoding="utf-8")

    def model_client(system_prompt, user_prompt, model=None, timeout=None):
        return (
            "FILE: hello.py\n"
            "SEARCH:\n"
            "def hello():\n"
            "    return False\n"
            "REPLACE:\n"
            "def hello():\n"
            "    return True\n"
            "END"
        )

    ctx = HealContext(
        op=OperationalContext(
            instance_id="t3",
            repo_dir=tmp_path,
            problem_statement="Change hello to return True",
            repro_script=(
                "from pathlib import Path\n"
                "assert 'return True' in Path('hello.py').read_text()\n"
            ),
            repro_evidence="AssertionError: return True missing",
            reproduced=True,
            localized_files=[("hello.py", target.read_text(encoding="utf-8"))],
            plan={"search_symbols": ["hello"], "repair_strategy": "rewrite hello"},
            max_tries=1,
        ),
        gov=GovernanceContext(),
    )

    orch = HealOrchestrator(
        phases=[
            PatchSynthesisPhase(SearchReplaceParser(), Patcher(), model_client),
            VerificationPhase(EvaluationGate(tmp_path)),
        ],
        governance_gate=GovernanceGate(),
    )

    res_ctx = orch.run(ctx)

    assert res_ctx.op.runner_completed is True
    assert res_ctx.op.solve_eligible is True
    assert res_ctx.gov.gate_exit == "verification"
    assert res_ctx.gov.stop_layer_matched is True
    assert res_ctx.gov.family_matched is True
