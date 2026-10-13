from __future__ import annotations


import pytest

from nexus.core.capability_selector import CapabilityConstraints, CapabilitySelector
from nexus.core.capability_signal_set import CapabilitySignalSet
from tests.integration.capability_plan_contract import (
    assert_planner_selection,
    assert_skip_env_is_inert,
)


def _make_sig(**kw):
    defaults = dict(
        task_id="test-e2e-s",
        task_desc="fix critical bug",
        risk_level="CRITICAL",
        impact_complexity=4.5,
        belief_confidence=0.3,
        skills_triggered=[],
        tenant_id="test",
    )
    defaults.update(kw)
    return CapabilitySignalSet(**defaults)


EXPECTED_PLAN = frozenset({
    "artifact_gate",
    "autoreason",
    "belief",
    "claim_gate",
    "codeintel",
    "drone",
    "forecast_pregate",
    "mempalace",
    "nightshift",
    "nightshift_runner_service",
    "sandbox_replay",
    "sandbox_runner",
    "swarm_multi_agent",
    "ultra_review",
})


def test_s_5_capabilities_invoked_in_real_task(monkeypatch, tmp_path):
    """Contract: the planner's selection for this task is exactly the planned set, and it is what runs."""
    assert_planner_selection(
        _make_sig(),
        EXPECTED_PLAN,
        absent=("policy_capability_gate", "entropy_guard_v2", "zero_trust_v2_behavior"),
        monkeypatch=monkeypatch,
        project_root=str(tmp_path),
    )


@pytest.mark.parametrize(
    "skip_cap,skip_env",
    [
        ("mempalace", "NEXUS_SKIP_MEMPALACE"),
        ("policy_capability_gate", "NEXUS_SKIP_POLICY_CAPABILITY_GATE"),
        ("entropy_guard_v2", "NEXUS_SKIP_ENTROPY_GUARD_V2"),
        ("zero_trust_v2_behavior", "NEXUS_SKIP_ZERO_TRUST_V2_BEHAVIOR"),
        ("nightshift_runner_service", "NEXUS_SKIP_NIGHTSHIFT_RUNNER_SERVICE"),
    ],
)
def test_s_5_capabilities_disable_each_breaks_task(skip_cap, skip_env, monkeypatch, tmp_path):
    """Contract: NEXUS_SKIP_* no longer changes the planner's selection (#514); the planner decides."""
    assert_skip_env_is_inert(
        _make_sig(), skip_cap, skip_env, monkeypatch=monkeypatch, project_root=str(tmp_path)
    )


def test_s_5_capabilities_receipts_persisted():
    """Verify plan contains S phase capability receipts."""
    sig = _make_sig()
    cs = CapabilitySelector(project_root="/tmp")
    plan = cs.select_capabilities(sig, CapabilityConstraints(project_root="/tmp"))
    assert len(plan.required_capabilities) > 0
    assert hasattr(plan, "phases")
    assert "S" in plan.phases


def test_s_5_capabilities_in_plan_dict():
    """Verify plan serialization contains all S phase caps."""
    sig = _make_sig()
    cs = CapabilitySelector(project_root="/tmp")
    plan = cs.select_capabilities(sig, CapabilityConstraints(project_root="/tmp"))
    plan_dict = plan.__dict__
    caps = plan_dict.get("required_capabilities", [])
    assert "mempalace" in caps
    assert "nightshift_runner_service" in caps
