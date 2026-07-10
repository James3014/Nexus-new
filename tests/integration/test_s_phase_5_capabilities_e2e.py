from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest

from nexus.core.capability_selector import CapabilitySelector, CapabilityConstraints
from nexus.core.capability_signal_set import CapabilitySignalSet


def _make_sig(**kw):
    defaults = dict(
        task_id="test-e2e-s", task_desc="fix critical bug",
        risk_level="CRITICAL", impact_complexity=4.5,
        belief_confidence=0.3, skills_triggered=[], tenant_id="test",
    )
    defaults.update(kw)
    return CapabilitySignalSet(**defaults)


def test_s_5_capabilities_invoked_in_real_task():
    """M1: S phase 5 capabilities must appear in plan for CRITICAL task."""
    sig = _make_sig()
    cs = CapabilitySelector(project_root="/tmp")
    plan = cs.select_capabilities(sig, CapabilityConstraints(project_root="/tmp"))
    caps = plan.required_capabilities
    for cap in ["mempalace", "policy_capability_gate", "entropy_guard_v2",
                 "zero_trust_v2_behavior", "nightshift_runner_service"]:
        assert cap in caps, f"S phase cap {cap} missing from plan: {caps}"


@pytest.mark.parametrize("skip_cap,skip_env", [
    ("mempalace", "NEXUS_SKIP_MEMPALACE"),
    ("policy_capability_gate", "NEXUS_SKIP_POLICY_CAPABILITY_GATE"),
    ("entropy_guard_v2", "NEXUS_SKIP_ENTROPY_GUARD_V2"),
    ("zero_trust_v2_behavior", "NEXUS_SKIP_ZERO_TRUST_V2_BEHAVIOR"),
    ("nightshift_runner_service", "NEXUS_SKIP_NIGHTSHIFT_RUNNER_SERVICE"),
])
def test_s_5_capabilities_disable_each_breaks_task(skip_cap, skip_env):
    """M2: Each S phase cap can be skipped via env flag."""
    os.environ[skip_env] = "1"
    try:
        sig = _make_sig()
        cs = CapabilitySelector(project_root="/tmp")
        plan = cs.select_capabilities(sig, CapabilityConstraints(project_root="/tmp"))
        caps = plan.required_capabilities
        assert skip_cap not in caps, (
            f"{skip_cap} should be skipped when {skip_env}=1, got: {caps}"
        )
    finally:
        os.environ.pop(skip_env, None)


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
