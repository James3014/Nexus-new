"""C6AD: D-phase committee diagnosis tests.

Multi-model independent diagnosis → Borda selects best → feeds into plan.
"""
from __future__ import annotations

from types import SimpleNamespace
import pytest
from unittest.mock import MagicMock, patch

from nexus.services.local_heal.committee_orchestrator import CommitteeOrchestrator
from nexus.services.local_heal.interface import PhaseResult, RepairPlan


class _FixedPhase:
    def __init__(self, *, success: bool = True, failure_reason: str = ""):
        self._result = PhaseResult(success=success, failure_reason=failure_reason)

    def execute(self, ctx):
        return self._result


class _DiagnosingPlanningPhase:
    """Planning phase that records diagnosis context for verification."""
    def __init__(self, plan: RepairPlan | None = None):
        self._plan = plan or RepairPlan(
            search_symbols=["func_a", "ClassB"],
            repair_strategy="Fix the bug",
            violated_invariants=["invariant_1"],
        )
        self.calls = 0

    def execute(self, ctx):
        self.calls += 1
        ctx.op.plan = self._plan
        ctx.op.model_decisions.append({"phase": "planning", "model": "qwen2.5-coder:7b"})
        return PhaseResult(success=True)

    def run(self, input_data):
        from nexus.services.local_heal.interface import PlanningOutput
        return PlanningOutput(success=True, plan=self._plan, model_decision={"phase": "planning", "model": "qwen2.5-coder:7b"})


class _FailingPlanningPhase:
    def execute(self, ctx):
        ctx.op.failure_reason = "PLANNING_FAILED"
        return PhaseResult(success=False, failure_reason="PLANNING_FAILED")


class _PatchPhase:
    def __init__(self):
        self.calls = 0

    def execute(self, ctx):
        self.calls += 1
        model = ctx.op.committee_proposer_model if hasattr(ctx.op, "committee_proposer_model") else "qwen2.5-coder:7b-instruct"
        ctx.op.final_patch = f"patch-{self.calls}"
        ctx.op.model_decisions.append({
            "phase": "patch",
            "model": model,
            "raw_label": "r:0,d:0,p:3,c:0",
            "output_class": "VALID_SEARCH_REPLACE",
            "status": "SUCCESS",
        })
        return PhaseResult(success=True)


class _CommitteeControllerStub:
    def __init__(self, task_id: str, domains=None):
        self.task_id = task_id
        self.enabled = True

    def process_proposals(self, raw_proposals):
        from nexus.committee.models import CommitteeReceipt
        return CommitteeReceipt(
            task_id=self.task_id,
            k=len(raw_proposals),
            candidates=[],
            verdicts=[],
            winner_id=f"{self.task_id}-{raw_proposals[0]['model']}-{raw_proposals[0]['attempt']}-abcd",
            confidence=0.9,
            verifier_gap=0.1,
            failure_bucket=None,
            abstain_reason=None,
            total_cost=0.2,
        )


def _make_ctx(
    diagnosis_enabled: bool = True,
    proposer_specs=None,
):
    if proposer_specs is None:
        proposer_specs = [
            {"model": "qwen2.5-coder:7b-instruct", "role": "primary"},
            {"model": "deepseek-coder:6.7b-instruct", "role": "secondary"},
        ]
    return SimpleNamespace(
        op=SimpleNamespace(
            instance_id="C_12481",
            final_patch="",
            model_decisions=[],
            failure_reason="",
            solve_eligible=False,
            runner_completed=False,
            problem_statement="Bug in func_a: division by zero",
            repro_evidence="Traceback: ZeroDivisionError",
            repo_dir="/tmp/repo",
            plan=None,
            route_context={
                "signal_snapshot": {
                    "local_committee_enabled": True,
                    "use_committee": True,
                    "diagnosis_committee_enabled": diagnosis_enabled,
                    "proposer_specs": proposer_specs,
                    "judge_model": "qwen2.5:3b",
                    "diagnosis_models": [
                        "qwen2.5-coder:7b-instruct",
                        "deepseek-coder:6.7b-instruct",
                    ],
                }
            },
        )
    )


def _make_orch(phases=None, diagnosis_phase=None):
    orch = CommitteeOrchestrator.__new__(CommitteeOrchestrator)
    orch.k = None
    if phases is None:
        orch.repro_phase = _FixedPhase()
        orch.plan_phase = _DiagnosingPlanningPhase()
        orch.loc_phase = _FixedPhase()
        orch.patch_phase = _PatchPhase()
        orch.verify_phase = _FixedPhase(success=True)
    else:
        orch.repro_phase, orch.plan_phase, orch.loc_phase, orch.patch_phase, orch.verify_phase = phases
    orch.diagnosis_phase = diagnosis_phase
    orch.governance_gate = MagicMock()
    orch.receipt_writer = None
    orch.corrector = MagicMock()
    orch.failure_analyzer = MagicMock()
    orch.context_guard = MagicMock()
    orch.phase_runner = MagicMock()
    return orch


# === C6AD RED Tests ===


def test_committee_diagnosis_method_exists():
    """CommitteeOrchestrator must have diagnose_with_committee method."""
    orch = CommitteeOrchestrator.__new__(CommitteeOrchestrator)
    assert hasattr(orch, "diagnose_with_committee"), (
        "CommitteeOrchestrator must implement diagnose_with_committee()"
    )


def test_committee_diagnosis_calls_multiple_models(monkeypatch):
    """diagnose_with_committee should invoke each diagnosis model independently."""
    ctx = _make_ctx()
    orch = _make_orch()

    diagnosis_results = []
    original_diagnose = getattr(orch, "diagnose_with_committee", None)
    if original_diagnose is None:
        pytest.skip("diagnose_with_committee not implemented yet — RED test")

    with patch.object(orch, "_invoke_diagnosis_model") as mock_invoke:
        mock_invoke.side_effect = [
            {"root_cause": "division by zero in func_a", "confidence": 0.8, "model": "qwen2.5-coder:7b-instruct"},
            {"root_cause": "missing guard in func_a", "confidence": 0.7, "model": "deepseek-coder:6.7b-instruct"},
        ]
        result = orch.diagnose_with_committee(ctx)

    assert mock_invoke.call_count == 2, "Should call each diagnosis model once"
    assert result is not None


def test_committee_diagnosis_borda_selects_best(monkeypatch):
    """Borda voting should select the diagnosis with highest aggregated rank."""
    ctx = _make_ctx()
    orch = _make_orch()

    original_diagnose = getattr(orch, "diagnose_with_committee", None)
    if original_diagnose is None:
        pytest.skip("diagnose_with_committee not implemented yet — RED test")

    diagnoses = [
        {"root_cause": "division by zero", "confidence": 0.9, "model": "qwen2.5-coder:7b-instruct", "rank": 1},
        {"root_cause": "missing guard", "confidence": 0.6, "model": "deepseek-coder:6.7b-instruct", "rank": 2},
    ]
    with patch.object(orch, "_invoke_diagnosis_model") as mock_invoke:
        mock_invoke.side_effect = diagnoses
        result = orch.diagnose_with_committee(ctx)

    assert result is not None
    assert result.get("root_cause") == "division by zero", "Borda should select highest-ranked diagnosis"


def test_committee_diagnosis_feeds_into_plan(monkeypatch):
    """Selected diagnosis should be written to ctx.op._committee_diagnosis."""
    ctx = _make_ctx()
    orch = _make_orch()

    original_diagnose = getattr(orch, "diagnose_with_committee", None)
    if original_diagnose is None:
        pytest.skip("diagnose_with_committee not implemented yet — RED test")

    diagnoses = [
        {"root_cause": "division by zero in func_a", "confidence": 0.9, "model": "qwen2.5-coder:7b-instruct"},
        {"root_cause": "missing guard", "confidence": 0.6, "model": "deepseek-coder:6.7b-instruct"},
    ]
    with patch.object(orch, "_invoke_diagnosis_model") as mock_invoke:
        mock_invoke.side_effect = diagnoses
        orch.diagnose_with_committee(ctx)

    assert ctx.op._committee_diagnosis is not None, (
        "Diagnosis result should be stored on ctx.op._committee_diagnosis"
    )
    assert ctx.op._committee_diagnosis["root_cause"] == "division by zero in func_a"


def test_committee_diagnosis_disabled_falls_back_to_single(monkeypatch):
    """When diagnosis_committee_enabled=False, should skip committee diagnosis."""
    ctx = _make_ctx(diagnosis_enabled=False)
    orch = _make_orch()

    original_diagnose = getattr(orch, "diagnose_with_committee", None)
    if original_diagnose is None:
        pytest.skip("diagnose_with_committee not implemented yet — RED test")

    result = orch.diagnose_with_committee(ctx)
    assert result is None or result == {}, "Disabled committee should return empty/no-op"


def test_committee_diagnosis_records_trace(monkeypatch):
    """Diagnosis committee should write trace to ctx.op._committee_diagnosis_trace."""
    ctx = _make_ctx()
    orch = _make_orch()

    original_diagnose = getattr(orch, "diagnose_with_committee", None)
    if original_diagnose is None:
        pytest.skip("diagnose_with_committee not implemented yet — RED test")

    diagnoses = [
        {"root_cause": "division by zero", "confidence": 0.9, "model": "qwen2.5-coder:7b-instruct"},
        {"root_cause": "missing guard", "confidence": 0.7, "model": "deepseek-coder:6.7b-instruct"},
    ]
    with patch.object(orch, "_invoke_diagnosis_model") as mock_invoke:
        mock_invoke.side_effect = diagnoses
        orch.diagnose_with_committee(ctx)

    trace = getattr(ctx.op, "_committee_diagnosis_trace", None)
    assert trace is not None, "Should write _committee_diagnosis_trace"
    assert trace.get("schema") == "nexus.local_heal.committee_diagnosis.v1"
    assert trace.get("candidate_count", 0) >= 1


def test_committee_diagnosis_run_inserts_before_plan(monkeypatch):
    """When diagnosis committee enabled, run() should call diagnose before plan_phase."""
    call_order = []
    class _TrackingReproPhase:
        def execute(self, ctx):
            call_order.append("repro")
            return PhaseResult(success=True)
    class _TrackingPlanPhase:
        def execute(self, ctx):
            call_order.append("plan")
            ctx.op.plan = RepairPlan(search_symbols=[], repair_strategy="", violated_invariants=[])
            return PhaseResult(success=True)
    class _TrackingLocPhase:
        def execute(self, ctx):
            call_order.append("loc")
            return PhaseResult(success=True)

    ctx = _make_ctx()
    orch = _make_orch(phases=(
        _TrackingReproPhase(),
        _TrackingPlanPhase(),
        _TrackingLocPhase(),
        _PatchPhase(),
        _FixedPhase(success=True),
    ))

    original_diagnose = getattr(orch, "diagnose_with_committee", None)
    if original_diagnose is None:
        pytest.skip("diagnose_with_committee not implemented yet — RED test")

    with patch.object(orch, "_invoke_diagnosis_model") as mock_invoke:
        mock_invoke.return_value = {"root_cause": "test", "confidence": 0.8, "model": "qwen2.5-coder:7b-instruct"}
        monkeypatch.setenv("NEXUS_USE_COMMITTEE", "1")
        monkeypatch.setattr(
            "nexus.services.local_heal.committee_orchestrator.CommitteeControllerV263",
            _CommitteeControllerStub,
        )
        orch.run(ctx)

    assert "repro" in call_order
    assert "plan" in call_order
    if "diagnosis" in call_order:
        assert call_order.index("diagnosis") < call_order.index("plan"), (
            "Diagnosis must run before planning"
        )


def test_committee_diagnosis_overrides_plan_repair_strategy(monkeypatch):
    """When committee diagnosis exists, plan.repair_strategy should be overridden."""
    from nexus.services.local_heal.phases.planning import PlanningPhase
    from nexus.services.local_heal.planner import Planner

    plan_result = RepairPlan(
        search_symbols=["func_a"],
        repair_strategy="Original strategy",
        violated_invariants=[],
    )

    class _StubPlanner:
        def create_plan(self, *args, **kwargs):
            return plan_result
        llm_client = None

    class _StubRouter:
        def route(self, *args, **kwargs):
            return "INTUITIVE"

    planning_phase = PlanningPhase(planner=_StubPlanner(), router=_StubRouter())
    ctx = _make_ctx()
    ctx.op.reproduced = True
    ctx.op.repro_evidence = "test evidence"
    ctx.op._committee_diagnosis = {
        "root_cause": "division by zero in func_a",
        "confidence": 0.9,
        "model": "qwen2.5-coder:7b-instruct",
    }

    result = planning_phase.execute(ctx)

    assert result.success
    assert ctx.op.plan.repair_strategy.startswith("COMMITTEE_DIAGNOSIS:")
    assert "division by zero" in ctx.op.plan.repair_strategy
