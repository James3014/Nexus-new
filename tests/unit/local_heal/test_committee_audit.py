"""C6AE: A-phase committee verification tests.

Multi-model independent verification → Borda selects best → feeds into verify.
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


class _VerifyPhase:
    def __init__(self, *, success: bool = True):
        self._success = success

    def execute(self, ctx):
        ctx.op.solve_eligible = self._success
        return PhaseResult(success=self._success)


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
    audit_enabled: bool = True,
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
            final_patch="diff --git a/app.py\n+def func_a():\n+    return 1",
            model_decisions=[],
            failure_reason="",
            solve_eligible=False,
            runner_completed=False,
            problem_statement="Bug in func_a",
            repro_evidence="Traceback",
            repo_dir="/tmp/repo",
            plan=RepairPlan(search_symbols=["func_a"], repair_strategy="Fix", violated_invariants=[]),
            route_context={
                "signal_snapshot": {
                    "local_committee_enabled": True,
                    "use_committee": True,
                    "audit_committee_enabled": audit_enabled,
                    "proposer_specs": proposer_specs,
                    "judge_model": "qwen2.5:3b",
                    "audit_models": [
                        "qwen2.5-coder:7b-instruct",
                        "deepseek-coder:6.7b-instruct",
                    ],
                }
            },
        )
    )


def _make_orch(phases=None):
    orch = CommitteeOrchestrator.__new__(CommitteeOrchestrator)
    orch.k = None
    if phases is None:
        orch.repro_phase = _FixedPhase()
        orch.plan_phase = _FixedPhase()
        orch.loc_phase = _FixedPhase()
        orch.patch_phase = _PatchPhase()
        orch.verify_phase = _VerifyPhase(success=True)
    else:
        orch.repro_phase, orch.plan_phase, orch.loc_phase, orch.patch_phase, orch.verify_phase = phases
    orch.governance_gate = MagicMock()
    orch.receipt_writer = None
    orch.corrector = MagicMock()
    orch.failure_analyzer = MagicMock()
    orch.context_guard = MagicMock()
    orch.phase_runner = MagicMock()
    return orch


# === C6AE RED Tests ===


def test_audit_with_committee_method_exists():
    """CommitteeOrchestrator must have audit_with_committee method."""
    orch = CommitteeOrchestrator.__new__(CommitteeOrchestrator)
    assert hasattr(orch, "audit_with_committee"), (
        "CommitteeOrchestrator must implement audit_with_committee()"
    )


def test_audit_with_committee_calls_multiple_models(monkeypatch):
    """audit_with_committee should invoke each audit model independently."""
    ctx = _make_ctx()
    orch = _make_orch()

    original_audit = getattr(orch, "audit_with_committee", None)
    if original_audit is None:
        pytest.skip("audit_with_committee not implemented yet — RED test")

    with patch.object(orch, "_invoke_audit_model") as mock_invoke:
        mock_invoke.side_effect = [
            {"verdict": "pass", "confidence": 0.9, "model": "qwen2.5-coder:7b-instruct", "reason": "patch looks correct"},
            {"verdict": "fail", "confidence": 0.7, "model": "deepseek-coder:6.7b-instruct", "reason": "missing error handling"},
        ]
        result = orch.audit_with_committee(ctx)

    assert mock_invoke.call_count == 2, "Should call each audit model once"
    assert result is not None


def test_audit_with_committee_borda_selects_best(monkeypatch):
    """Borda voting should select the audit with highest aggregated rank."""
    ctx = _make_ctx()
    orch = _make_orch()

    original_audit = getattr(orch, "audit_with_committee", None)
    if original_audit is None:
        pytest.skip("audit_with_committee not implemented yet — RED test")

    audits = [
        {"verdict": "pass", "confidence": 0.9, "model": "qwen2.5-coder:7b-instruct", "rank": 1},
        {"verdict": "fail", "confidence": 0.6, "model": "deepseek-coder:6.7b-instruct", "rank": 2},
    ]
    with patch.object(orch, "_invoke_audit_model") as mock_invoke:
        mock_invoke.side_effect = audits
        result = orch.audit_with_committee(ctx)

    assert result is not None
    assert result.get("verdict") == "pass", "Borda should select highest-ranked audit"


def test_audit_with_committee_records_trace(monkeypatch):
    """Audit committee should write trace to ctx.op._committee_audit_trace."""
    ctx = _make_ctx()
    orch = _make_orch()

    original_audit = getattr(orch, "audit_with_committee", None)
    if original_audit is None:
        pytest.skip("audit_with_committee not implemented yet — RED test")

    audits = [
        {"verdict": "pass", "confidence": 0.9, "model": "qwen2.5-coder:7b-instruct"},
        {"verdict": "fail", "confidence": 0.7, "model": "deepseek-coder:6.7b-instruct"},
    ]
    with patch.object(orch, "_invoke_audit_model") as mock_invoke:
        mock_invoke.side_effect = audits
        orch.audit_with_committee(ctx)

    trace = getattr(ctx.op, "_committee_audit_trace", None)
    assert trace is not None, "Should write _committee_audit_trace"
    assert trace.get("schema") == "nexus.local_heal.committee_audit.v1"
    assert trace.get("candidate_count", 0) >= 1


def test_audit_with_committee_disabled_returns_none(monkeypatch):
    """When audit_committee_enabled=False, should skip committee audit."""
    ctx = _make_ctx(audit_enabled=False)
    orch = _make_orch()

    original_audit = getattr(orch, "audit_with_committee", None)
    if original_audit is None:
        pytest.skip("audit_with_committee not implemented yet — RED test")

    result = orch.audit_with_committee(ctx)
    assert result is None or result == {}, "Disabled committee should return empty/no-op"


def test_audit_with_committee_pass_updates_solve_eligible(monkeypatch):
    """When audit verdict is pass, solve_eligible should be set to True."""
    ctx = _make_ctx()
    ctx.op.solve_eligible = False
    orch = _make_orch()

    original_audit = getattr(orch, "audit_with_committee", None)
    if original_audit is None:
        pytest.skip("audit_with_committee not implemented yet — RED test")

    audits = [
        {"verdict": "pass", "confidence": 0.9, "model": "qwen2.5-coder:7b-instruct"},
        {"verdict": "pass", "confidence": 0.8, "model": "deepseek-coder:6.7b-instruct"},
    ]
    with patch.object(orch, "_invoke_audit_model") as mock_invoke:
        mock_invoke.side_effect = audits
        orch.audit_with_committee(ctx)

    assert ctx.op.solve_eligible is True, "Pass verdict should set solve_eligible=True"


def test_audit_with_committee_fail_updates_failure_reason(monkeypatch):
    """When audit verdict is fail, failure_reason should be set."""
    ctx = _make_ctx()
    ctx.op.solve_eligible = True
    orch = _make_orch()

    original_audit = getattr(orch, "audit_with_committee", None)
    if original_audit is None:
        pytest.skip("audit_with_committee not implemented yet — RED test")

    audits = [
        {"verdict": "fail", "confidence": 0.9, "model": "qwen2.5-coder:7b-instruct", "reason": "missing guard"},
        {"verdict": "fail", "confidence": 0.8, "model": "deepseek-coder:6.7b-instruct", "reason": "incomplete fix"},
    ]
    with patch.object(orch, "_invoke_audit_model") as mock_invoke:
        mock_invoke.side_effect = audits
        orch.audit_with_committee(ctx)

    assert ctx.op.solve_eligible is False, "Fail verdict should set solve_eligible=False"
    assert "COMMITTEE_AUDIT_REJECTION" in ctx.op.failure_reason or ctx.op.failure_reason != ""
