from __future__ import annotations

import os

import pytest

from nexus.core.capability_selector import CapabilitySelector, CapabilityConstraints
from nexus.core.capability_signal_set import CapabilitySignalSet


def _make_sig(**kw):
    defaults = dict(
        task_id="test-e2e-p", task_desc="apply formula rule for high impact bug",
        risk_level="HIGH", impact_complexity=3.5,
        belief_confidence=0.7, skills_triggered=[], tenant_id="test",
    )
    defaults.update(kw)
    return CapabilitySignalSet(**defaults)


@pytest.mark.parametrize("skip_cap,skip_env", [
    ("autonomic_router", "NEXUS_SKIP_AUTONOMIC_ROUTER"),
    ("predictive_auditor", "NEXUS_SKIP_PREDICTIVE_AUDITOR"),
    ("spec_guarded", "NEXUS_SKIP_SPEC_GUARDED"),
    ("decision_formula_engine", "NEXUS_SKIP_DECISION_FORMULA_ENGINE"),
])
def test_p_4_capabilities_disable_each_breaks_task(skip_cap, skip_env):
    """M2: Each P phase cap can be skipped via env flag."""
    os.environ[skip_env] = "1"
    try:
        sig = _make_sig()
        plan = CapabilitySelector(project_root="/tmp").select_capabilities(
            sig, CapabilityConstraints(project_root="/tmp"))
        assert skip_cap not in plan.required_capabilities
    finally:
        os.environ.pop(skip_env, None)


def test_p_4_capabilities_invoked_in_real_task():
    """M1: P phase 4 capabilities appear in plan."""
    sig = _make_sig()
    plan = CapabilitySelector(project_root="/tmp").select_capabilities(
        sig, CapabilityConstraints(project_root="/tmp"))
    caps = plan.required_capabilities
    for cap in ["autonomic_router", "predictive_auditor", "spec_guarded"]:
        assert cap in caps, f"P phase cap {cap} missing: {caps}"
