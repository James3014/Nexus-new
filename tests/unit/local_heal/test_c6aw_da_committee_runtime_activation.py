"""
C6AW: D/A Committee Runtime Activation Proof.
Verifies D/A committee gates are now injected by planner, gate-open path
no longer returns None, and fail-closed behavior is preserved when gate absent.
"""
import os
import inspect
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path


def _make_ctx(signal_snapshot: dict):
    from nexus.services.local_heal.context import HealContext, GovernanceContext, OperationalContext
    return HealContext(
        op=OperationalContext(
            instance_id="test-c6aw",
            repo_dir=Path("/tmp"),
            problem_statement="test",
            route_context={"signal_snapshot": signal_snapshot},
        ),
        gov=GovernanceContext(),
    )


_PLANNER_ENV = {
    "NEXUS_ENABLE_LOCAL_MODEL_EXECUTOR": "1",
    "NEXUS_LOCAL_MODEL_EXECUTOR_TOPOLOGY": "local_committee_only",
    "NEXUS_LOCAL_MODEL_EXECUTOR_PROVIDER": "ollama",
    "NEXUS_LOCAL_MODEL_EXECUTOR_MODEL": "qwen2.5-coder:7b-instruct",
    "NEXUS_C15_PRIMARY_PROPOSER_MODEL": "qwen2.5-coder:7b-instruct",
    "NEXUS_C15_SECONDARY_PROPOSER_MODEL": "deepseek-coder:6.7b-instruct",
    "NEXUS_C15_JUDGE_MODEL": "qwen2.5-s2t-advisor:3b",
}


# ─── Phase 2.1: Planner injects 4 D/A gate fields ───

def test_planner_injects_diagnosis_committee_enabled():
    from nexus.engine.capability_planner import CapabilityPlanner
    with patch.dict(os.environ, _PLANNER_ENV, clear=False):
        planner = CapabilityPlanner()
        plan = planner.plan(task_desc="test", task_type="bugfix", route={"recommended_flow": "local_heal"})
        ss = plan.signal_snapshot
        assert ss["diagnosis_committee_enabled"] is True


def test_planner_injects_audit_committee_enabled():
    from nexus.engine.capability_planner import CapabilityPlanner
    with patch.dict(os.environ, _PLANNER_ENV, clear=False):
        planner = CapabilityPlanner()
        plan = planner.plan(task_desc="test", task_type="bugfix", route={"recommended_flow": "local_heal"})
        ss = plan.signal_snapshot
        assert ss["audit_committee_enabled"] is True


def test_planner_injects_diagnosis_models():
    from nexus.engine.capability_planner import CapabilityPlanner
    with patch.dict(os.environ, _PLANNER_ENV, clear=False):
        planner = CapabilityPlanner()
        plan = planner.plan(task_desc="test", task_type="bugfix", route={"recommended_flow": "local_heal"})
        ss = plan.signal_snapshot
        assert len(ss["diagnosis_models"]) >= 2
        assert "qwen2.5-coder:7b-instruct" in ss["diagnosis_models"]
        assert "deepseek-coder:6.7b-instruct" in ss["diagnosis_models"]


def test_planner_injects_audit_models():
    from nexus.engine.capability_planner import CapabilityPlanner
    with patch.dict(os.environ, _PLANNER_ENV, clear=False):
        planner = CapabilityPlanner()
        plan = planner.plan(task_desc="test", task_type="bugfix", route={"recommended_flow": "local_heal"})
        ss = plan.signal_snapshot
        assert len(ss["audit_models"]) >= 2


def test_planner_diagnosis_models_env_override():
    from nexus.engine.capability_planner import CapabilityPlanner
    env = {**_PLANNER_ENV, "NEXUS_C15_DIAGNOSIS_MODELS": "model-a,model-b"}
    with patch.dict(os.environ, env, clear=False):
        planner = CapabilityPlanner()
        plan = planner.plan(task_desc="test", task_type="bugfix", route={"recommended_flow": "local_heal"})
        ss = plan.signal_snapshot
        assert ss["diagnosis_models"] == ["model-a", "model-b"]


# ─── Phase 2.2: Gate-open path no longer returns None (mocked LLM) ───

def test_diagnose_gate_open_does_not_return_none():
    """With gate=True + ≥2 models + mocked LLM, diagnose_with_committee returns selected dict."""
    from nexus.services.local_heal.committee_orchestrator import CommitteeOrchestrator
    ctx = _make_ctx({
        "diagnosis_committee_enabled": True,
        "diagnosis_models": ["qwen2.5-coder:7b-instruct", "deepseek-coder:6.7b-instruct"],
    })
    orch = CommitteeOrchestrator.__new__(CommitteeOrchestrator)
    mock_result = {"model": "qwen2.5-coder:7b-instruct", "status": "success", "confidence": 0.8, "root_cause": "test"}
    with patch.object(orch, "_invoke_diagnosis_model", return_value=mock_result):
        result = orch.diagnose_with_committee(ctx)
    assert result is not None, "D committee must not return None when gate is open"
    assert result.get("model") == "qwen2.5-coder:7b-instruct"
    # Telemetry
    assert getattr(ctx.op, "_diagnosis_committee_enabled_runtime", False) is True
    assert getattr(ctx.op, "_diagnosis_committee_invoked", False) is True
    assert getattr(ctx.op, "_diagnosis_committee_selected_model", "") == "qwen2.5-coder:7b-instruct"


def test_audit_gate_open_does_not_return_none():
    """With gate=True + ≥2 models + mocked LLM, audit_with_committee returns selected dict."""
    from nexus.services.local_heal.committee_orchestrator import CommitteeOrchestrator
    ctx = _make_ctx({
        "audit_committee_enabled": True,
        "audit_models": ["qwen2.5-coder:7b-instruct", "deepseek-coder:6.7b-instruct"],
    })
    orch = CommitteeOrchestrator.__new__(CommitteeOrchestrator)
    mock_result = {"model": "qwen2.5-coder:7b-instruct", "status": "success", "verdict": "pass", "confidence": 0.8, "reason": "ok"}
    with patch.object(orch, "_invoke_audit_model", return_value=mock_result):
        result = orch.audit_with_committee(ctx)
    assert result is not None, "A committee must not return None when gate is open"
    assert result.get("verdict") == "pass"
    # Telemetry
    assert getattr(ctx.op, "_audit_committee_enabled_runtime", False) is True
    assert getattr(ctx.op, "_audit_committee_invoked", False) is True
    assert getattr(ctx.op, "_audit_committee_selected_model", "") == "qwen2.5-coder:7b-instruct"


# ─── Phase 2.3: Fail-closed preserved when gate absent ───

def test_diagnose_fail_closed_when_gate_absent():
    """When diagnosis_committee_enabled is absent, still returns None + telemetry shows gate=False."""
    from nexus.services.local_heal.committee_orchestrator import CommitteeOrchestrator
    ctx = _make_ctx({"local_committee_enabled": True})
    orch = CommitteeOrchestrator.__new__(CommitteeOrchestrator)
    result = orch.diagnose_with_committee(ctx)
    assert result is None
    assert getattr(ctx.op, "_diagnosis_committee_enabled_runtime", None) is False
    assert getattr(ctx.op, "_diagnosis_committee_invoked", None) is False


def test_audit_fail_closed_when_gate_absent():
    """When audit_committee_enabled is absent, still returns None + telemetry shows gate=False."""
    from nexus.services.local_heal.committee_orchestrator import CommitteeOrchestrator
    ctx = _make_ctx({"local_committee_enabled": True})
    orch = CommitteeOrchestrator.__new__(CommitteeOrchestrator)
    result = orch.audit_with_committee(ctx)
    assert result is None
    assert getattr(ctx.op, "_audit_committee_enabled_runtime", None) is False
    assert getattr(ctx.op, "_audit_committee_invoked", None) is False


def test_planner_snapshot_activates_both_gates():
    """Planner's actual snapshot now opens both D/A gates — no longer return None."""


# ─── C6AX: Bridge verification — local_committee_only path calls D/A ───

def test_local_committee_only_branch_bridges_da_committee():
    """C6AX: local_committee_only branch in LocalModelExecutor._run_impl() must call
    diagnose_with_committee() before candidate generation and
    audit_with_committee() after winner selection."""
    import inspect
    from nexus.services.local_heal.local_model_executor import LocalModelExecutor
    source = inspect.getsource(LocalModelExecutor._run_impl)
    assert "diagnose_with_committee" in source, "D-phase bridge missing in local_committee_only path"
    assert "audit_with_committee" in source, "A-phase bridge missing in local_committee_only path"
    assert "diagnosis_committee_invoked" in source, "D telemetry recording missing"
    assert "audit_committee_invoked" in source, "A telemetry recording missing"
    # Verify D comes before R-phase (candidate generation)
    d_pos = source.index("diagnose_with_committee")
    r_pos = source.index("generate_committee_candidates")
    a_pos = source.index("audit_with_committee")
    assert d_pos < r_pos, "D-phase must run BEFORE candidate generation (R-phase)"
    assert r_pos < a_pos, "A-phase must run AFTER candidate generation (R-phase)"

    from nexus.engine.capability_planner import CapabilityPlanner
    from nexus.services.local_heal.committee_orchestrator import CommitteeOrchestrator
    with patch.dict(os.environ, _PLANNER_ENV, clear=False):
        planner = CapabilityPlanner()
        plan = planner.plan(task_desc="test", task_type="bugfix", route={"recommended_flow": "local_heal"})
        ss = plan.signal_snapshot
    ctx = _make_ctx(ss)
    orch = CommitteeOrchestrator.__new__(CommitteeOrchestrator)
    # D gate: should NOT return None at gate check (will fail later at LLM, but gate passes)
    mock_diag = {"model": "test", "status": "success", "confidence": 0.5, "root_cause": "x"}
    with patch.object(orch, "_invoke_diagnosis_model", return_value=mock_diag):
        d_result = orch.diagnose_with_committee(ctx)
    assert d_result is not None, "D committee gate now opens with planner snapshot"
    # A gate
    mock_audit = {"model": "test", "status": "success", "verdict": "pass", "confidence": 0.5, "reason": "x"}
    with patch.object(orch, "_invoke_audit_model", return_value=mock_audit):
        a_result = orch.audit_with_committee(ctx)
    assert a_result is not None, "A committee gate now opens with planner snapshot"
