from __future__ import annotations

import os

import pytest

from nexus.core.capability_selector import CapabilitySelector, CapabilityConstraints
from nexus.core.capability_signal_set import CapabilitySignalSet


def _make_sig(**kw):
    defaults = dict(
        task_id="test-e2e-d", task_desc="ambiguous decision needed",
        risk_level="CRITICAL", impact_complexity=4.0,
        belief_confidence=0.3, skills_triggered=[], tenant_id="test",
    )
    defaults.update(kw)
    return CapabilitySignalSet(**defaults)


def test_d_2_capabilities_invoked_in_real_task():
    """M1: D phase 2 capabilities appear in plan."""
    sig = _make_sig()
    plan = CapabilitySelector(project_root="/tmp").select_capabilities(
        sig, CapabilityConstraints(project_root="/tmp"))
    caps = plan.required_capabilities
    for cap in ["belief", "autoreason"]:
        assert cap in caps, f"D phase cap {cap} missing: {caps}"


@pytest.mark.parametrize("skip_cap,skip_env", [
    ("belief", "NEXUS_SKIP_BELIEF"),
    ("autoreason", "NEXUS_SKIP_AUTOREASON"),
])
def test_d_2_capabilities_disable_each_breaks_task(skip_cap, skip_env):
    """M2: Each D phase cap can be skipped via env flag."""
    os.environ[skip_env] = "1"
    try:
        sig = _make_sig()
        plan = CapabilitySelector(project_root="/tmp").select_capabilities(
            sig, CapabilityConstraints(project_root="/tmp"))
        assert skip_cap not in plan.required_capabilities
    finally:
        os.environ.pop(skip_env, None)
