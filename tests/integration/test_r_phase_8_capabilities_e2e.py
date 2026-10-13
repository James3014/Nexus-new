from __future__ import annotations


import pytest

from nexus.core.capability_signal_set import CapabilitySignalSet
from tests.integration.capability_plan_contract import (
    assert_planner_selection,
    assert_skip_env_is_inert,
)


def _make_sig_critical(**kw):
    defaults = dict(
        task_id="test-e2e-r",
        task_desc="fix background battle campaign overnight bug",
        risk_level="CRITICAL",
        impact_complexity=4.5,
        belief_confidence=0.5,
        skills_triggered=[],
        tenant_id="test",
    )
    defaults.update(kw)
    return CapabilitySignalSet(**defaults)


def _make_sig_low(**kw):
    defaults = dict(
        task_id="test-e2e-r-low",
        task_desc="simple background fix",
        risk_level="LOW",
        impact_complexity=2.0,
        belief_confidence=0.9,
        skills_triggered=[],
        tenant_id="test",
    )
    defaults.update(kw)
    return CapabilitySignalSet(**defaults)


M1_CAPS_CRITICAL = [
    "hyper_sprint",
    "swarm_multi_agent",
    "drone",
    "nightshift",
    "battle_swarm",
    "sandbox_runner",
    "dual_loop",
]

M1_CAPS_LOW = [
    "repair_loop",
]

M2_CAPS = [
    ("hyper_sprint", "NEXUS_SKIP_HYPER_SPRINT"),
    ("swarm_multi_agent", "NEXUS_SKIP_SWARM_MULTI_AGENT"),
    ("drone", "NEXUS_SKIP_DRONE"),
    ("nightshift", "NEXUS_SKIP_NIGHTSHIFT"),
    ("battle_swarm", "NEXUS_SKIP_BATTLE_SWARM"),
    ("sandbox_runner", "NEXUS_SKIP_SANDBOX_RUNNER"),
    ("dual_loop", "NEXUS_SKIP_DUAL_LOOP"),
]

EXPECTED_PLAN_CRITICAL = frozenset({
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

EXPECTED_PLAN_LOW = frozenset({
    "artifact_gate",
    "claim_gate",
    "mempalace",
})


def test_r_8_capabilities_invoked_in_real_task(monkeypatch, tmp_path):
    """Contract: the planner's selection for this task is exactly the planned set, and it is what runs."""
    assert_planner_selection(
        _make_sig_critical(),
        EXPECTED_PLAN_CRITICAL,
        absent=("hyper_sprint", "battle_swarm", "dual_loop"),
        monkeypatch=monkeypatch,
        project_root=str(tmp_path),
    )


def test_r_repair_loop_invoked_for_low_risk(monkeypatch, tmp_path):
    """Contract: low-risk tasks plan only the gate/memory caps; repair_loop is not selected."""
    assert_planner_selection(
        _make_sig_low(),
        EXPECTED_PLAN_LOW,
        absent=("repair_loop", "hyper_sprint"),
        monkeypatch=monkeypatch,
        project_root=str(tmp_path),
    )


@pytest.mark.parametrize("skip_cap,skip_env", M2_CAPS)
def test_r_8_capabilities_disable_each_breaks_task(skip_cap, skip_env, monkeypatch, tmp_path):
    """Contract: NEXUS_SKIP_* no longer changes the planner's selection (#514); the planner decides."""
    assert_skip_env_is_inert(
        _make_sig_critical(), skip_env, monkeypatch=monkeypatch, project_root=str(tmp_path)
    )
