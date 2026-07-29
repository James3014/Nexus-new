"""
C6AV: Committee Solve Reality Check — Phase 0 Truth Audit.
Verifies whether D/A committee and R-phase committee are actually active
in the production solve path, without requiring live Ollama models.
"""
import os
import inspect
import pytest
from unittest.mock import patch


# ─── Phase 0.1: D/A committee gate flags are never injected by planner ───

def test_planner_does_not_inject_diagnosis_committee_enabled():
    """CapabilityPlanner must NOT inject diagnosis_committee_enabled for local_committee_only."""
    from nexus.engine.capability_planner import CapabilityPlanner
    env_vars = {
        "NEXUS_ENABLE_LOCAL_MODEL_EXECUTOR": "1",
        "NEXUS_LOCAL_MODEL_EXECUTOR_TOPOLOGY": "local_committee_only",
        "NEXUS_LOCAL_MODEL_EXECUTOR_PROVIDER": "ollama",
        "NEXUS_LOCAL_MODEL_EXECUTOR_MODEL": "qwen2.5-coder:7b-instruct",
        "NEXUS_C15_PRIMARY_PROPOSER_MODEL": "qwen2.5-coder:7b-instruct",
        "NEXUS_C15_SECONDARY_PROPOSER_MODEL": "deepseek-coder:6.7b-instruct",
        "NEXUS_C15_JUDGE_MODEL": "qwen2.5-s2t-advisor:3b",
    }
    with patch.dict(os.environ, env_vars, clear=False):
        planner = CapabilityPlanner()
        plan = planner.plan(task_desc="test", task_type="bugfix", route={"recommended_flow": "local_heal"})
        ss = plan.signal_snapshot
        assert ss["local_committee_enabled"] is True
        assert "proposer_specs" in ss
        assert "judge_model" in ss
        # C6AW: D/A gates now injected by planner (previously absent)
        assert ss.get("diagnosis_committee_enabled") is True, "D-phase gate now injected by planner (C6AW)"
        assert ss.get("audit_committee_enabled") is True, "A-phase gate now injected by planner (C6AW)"
        assert len(ss.get("diagnosis_models", [])) >= 2
        assert len(ss.get("audit_models", [])) >= 2


# ─── Phase 0.2: D/A committee gate returns None when flag absent ───

def _make_ctx(signal_snapshot: dict):
    from pathlib import Path
    from nexus.services.local_heal.context import HealContext, GovernanceContext, OperationalContext
    return HealContext(
        op=OperationalContext(
            instance_id="test-c6av",
            repo_dir=Path("/tmp"),
            problem_statement="test",
            route_context={"signal_snapshot": signal_snapshot},
        ),
        gov=GovernanceContext(),
    )


def test_diagnose_returns_none_when_gate_absent():
    """diagnose_with_committee() must return None when diagnosis_committee_enabled is absent."""
    from nexus.services.local_heal.committee_orchestrator import CommitteeOrchestrator
    ctx = _make_ctx({"local_committee_enabled": True})
    orch = CommitteeOrchestrator.__new__(CommitteeOrchestrator)
    assert orch.diagnose_with_committee(ctx) is None


def test_audit_returns_none_when_gate_absent():
    """audit_with_committee() must return None when audit_committee_enabled is absent."""
    from nexus.services.local_heal.committee_orchestrator import CommitteeOrchestrator
    ctx = _make_ctx({"local_committee_enabled": True})
    orch = CommitteeOrchestrator.__new__(CommitteeOrchestrator)
    assert orch.audit_with_committee(ctx) is None


def test_diagnose_returns_none_when_enabled_but_single_model():
    """Even if flag is True, <2 diagnosis_models means return None."""
    from nexus.services.local_heal.committee_orchestrator import CommitteeOrchestrator
    ctx = _make_ctx({"diagnosis_committee_enabled": True, "diagnosis_models": ["qwen2.5-coder:7b-instruct"]})
    orch = CommitteeOrchestrator.__new__(CommitteeOrchestrator)
    assert orch.diagnose_with_committee(ctx) is None


# ─── Phase 0.3: R-phase committee IS active ───

def test_r_phase_committee_active():
    """R-phase committee (proposer collection) requires proposer_specs which ARE injected."""
    from nexus.engine.capability_planner import CapabilityPlanner
    env_vars = {
        "NEXUS_ENABLE_LOCAL_MODEL_EXECUTOR": "1",
        "NEXUS_LOCAL_MODEL_EXECUTOR_TOPOLOGY": "local_committee_only",
        "NEXUS_LOCAL_MODEL_EXECUTOR_PROVIDER": "ollama",
        "NEXUS_LOCAL_MODEL_EXECUTOR_MODEL": "qwen2.5-coder:7b-instruct",
        "NEXUS_C15_PRIMARY_PROPOSER_MODEL": "qwen2.5-coder:7b-instruct",
        "NEXUS_C15_SECONDARY_PROPOSER_MODEL": "deepseek-coder:6.7b-instruct",
        "NEXUS_C15_JUDGE_MODEL": "qwen2.5-s2t-advisor:3b",
    }
    with patch.dict(os.environ, env_vars, clear=False):
        planner = CapabilityPlanner()
        plan = planner.plan(task_desc="test", task_type="bugfix", route={"recommended_flow": "local_heal"})
        ss = plan.signal_snapshot
        assert len(ss["proposer_specs"]) == 2
        models = [s["model"] for s in ss["proposer_specs"]]
        assert len(set(models)) == 2, "proposer models must be distinct"
        assert ss["judge_model"] not in models, "judge must not be a proposer"


def test_t3c1_projects_planner_members_without_route_mutation():
    from nexus.services.local_heal.committee_routed_tool import build_committee_member_demands

    snapshot = {
        "proposer_specs": [{"model": "a", "role": "primary"}, {"model": "b", "role": "secondary"}],
        "judge_model": "judge",
        "diagnosis_models": ["a", "b"],
        "audit_models": ["a", "b"],
        "delegated_retry_candidate_models": ["a", "b"],
        "route_authority": "CapabilityPlanner",
    }
    result = build_committee_member_demands(snapshot, parent_demand_id="demand_local")
    assert result["wiring_status"] == "WIRED"
    assert result["failure_reasons"] == []
    assert len(result["demands"]) == 9
    assert {item["phase"] for item in result["demands"]} == {
        "proposal", "judge", "diagnosis", "audit", "delegated_retry"
    }
    assert all(item["parent_demand_id"] == "demand_local" for item in result["demands"])
    assert all(item["route_authority"] == "CapabilityPlanner" for item in result["demands"])
    assert snapshot["proposer_specs"][0] == {"model": "a", "role": "primary"}


def test_t3c1_missing_member_fails_closed_without_replacement():
    from nexus.services.local_heal.committee_routed_tool import build_committee_member_demands

    result = build_committee_member_demands(
        {"proposer_specs": [{"model": "a", "role": "primary"}], "judge_model": "judge"},
        parent_demand_id="demand_local",
    )
    assert result["wiring_status"] == "FAIL_CLOSED"
    assert "proposal:requires_at_least_two_members" in result["failure_reasons"]
    assert "missing_diagnosis_models" not in result["failure_reasons"]


# ─── Phase 0.4: run() calls D/A but both no-op; parent does NOT ───

def test_run_calls_diagnose_and_audit():
    """CommitteeOrchestrator.run() source must contain D/A committee calls."""
    from nexus.services.local_heal.committee_orchestrator import CommitteeOrchestrator
    src = inspect.getsource(CommitteeOrchestrator.run)
    assert "diagnose_with_committee" in src
    assert "audit_with_committee" in src
    assert "verify_phase" in src


def test_parent_orchestrator_has_no_diagnose_or_audit():
    """HealOrchestrator (parent) must NOT have D/A committee methods."""
    from nexus.services.local_heal.orchestrator import HealOrchestrator
    assert not hasattr(HealOrchestrator, "diagnose_with_committee")
    assert not hasattr(HealOrchestrator, "audit_with_committee")
    parent_src = inspect.getsource(HealOrchestrator.run)
    assert "diagnose_with_committee" not in parent_src
    assert "audit_with_committee" not in parent_src


def test_da_committee_gates_open_with_planner_snapshot():
    """C6AW: With planner's actual signal_snapshot, both D/A gates are now OPEN.
    Gate check passes (no longer returns None at gate). LLM calls mocked to avoid live Ollama."""
    from nexus.engine.capability_planner import CapabilityPlanner
    from nexus.services.local_heal.committee_orchestrator import CommitteeOrchestrator
    env_vars = {
        "NEXUS_ENABLE_LOCAL_MODEL_EXECUTOR": "1",
        "NEXUS_LOCAL_MODEL_EXECUTOR_TOPOLOGY": "local_committee_only",
        "NEXUS_LOCAL_MODEL_EXECUTOR_PROVIDER": "ollama",
        "NEXUS_LOCAL_MODEL_EXECUTOR_MODEL": "qwen2.5-coder:7b-instruct",
    }
    with patch.dict(os.environ, env_vars, clear=False):
        planner = CapabilityPlanner()
        plan = planner.plan(task_desc="test", task_type="bugfix", route={"recommended_flow": "local_heal"})
        ss = plan.signal_snapshot
    ctx = _make_ctx(ss)
    orch = CommitteeOrchestrator.__new__(CommitteeOrchestrator)
    # D gate now opens — mock LLM to return valid result
    mock_d = {"model": "test", "status": "success", "confidence": 0.5, "root_cause": "x"}
    with patch.object(orch, "_invoke_diagnosis_model", return_value=mock_d):
        d_result = orch.diagnose_with_committee(ctx)
    assert d_result is not None, "D gate now opens with planner snapshot (C6AW)"
    # A gate now opens
    mock_a = {"model": "test", "status": "success", "verdict": "pass", "confidence": 0.5, "reason": "x"}
    with patch.object(orch, "_invoke_audit_model", return_value=mock_a):
        a_result = orch.audit_with_committee(ctx)
    assert a_result is not None, "A gate now opens with planner snapshot (C6AW)"
