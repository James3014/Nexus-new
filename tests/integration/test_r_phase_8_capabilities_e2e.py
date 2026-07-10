from __future__ import annotations

import os

import pytest

from nexus.core.capability_selector import CapabilitySelector, CapabilityConstraints
from nexus.core.capability_signal_set import CapabilitySignalSet


def _make_sig_critical(**kw):
    defaults = dict(
        task_id="test-e2e-r", task_desc="fix background battle campaign overnight bug",
        risk_level="CRITICAL", impact_complexity=4.5,
        belief_confidence=0.5, skills_triggered=[], tenant_id="test",
    )
    defaults.update(kw)
    return CapabilitySignalSet(**defaults)


def _make_sig_low(**kw):
    defaults = dict(
        task_id="test-e2e-r-low", task_desc="simple background fix",
        risk_level="LOW", impact_complexity=2.0,
        belief_confidence=0.9, skills_triggered=[], tenant_id="test",
    )
    defaults.update(kw)
    return CapabilitySignalSet(**defaults)


M1_CAPS_CRITICAL = [
    "hyper_sprint", "swarm_multi_agent",
    "drone", "nightshift", "battle_swarm", "sandbox_runner", "dual_loop",
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


def test_r_8_capabilities_invoked_in_real_task():
    """M1: R phase capabilities appear in plan for CRITICAL+battle task."""
    sig = _make_sig_critical()
    plan = CapabilitySelector(project_root="/tmp").select_capabilities(
        sig, CapabilityConstraints(project_root="/tmp"))
    caps = plan.required_capabilities
    for cap in M1_CAPS_CRITICAL:
        assert cap in caps, f"R phase cap {cap} missing: {caps}"


def test_r_repair_loop_invoked_for_low_risk():
    """M1: repair_loop selected for low-risk tasks (not hyper_sprint)."""
    sig = _make_sig_low()
    plan = CapabilitySelector(project_root="/tmp").select_capabilities(
        sig, CapabilityConstraints(project_root="/tmp"))
    caps = plan.required_capabilities
    assert "repair_loop" in caps, f"repair_loop missing for low-risk: {caps}"


@pytest.mark.parametrize("skip_cap,skip_env", M2_CAPS)
def test_r_8_capabilities_disable_each_breaks_task(skip_cap, skip_env):
    """M2: Each R phase cap can be skipped via env flag."""
    os.environ[skip_env] = "1"
    try:
        sig = _make_sig_critical()
        plan = CapabilitySelector(project_root="/tmp").select_capabilities(
            sig, CapabilityConstraints(project_root="/tmp"))
        assert skip_cap not in plan.required_capabilities
    finally:
        os.environ.pop(skip_env, None)
