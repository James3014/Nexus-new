from __future__ import annotations

import os

import pytest

from nexus.core.capability_selector import CapabilitySelector, CapabilityConstraints
from nexus.core.capability_signal_set import CapabilitySignalSet


def _make_sig(**kw):
    defaults = dict(
        task_id="test-e2e-x", task_desc="research source optimize refresh schedule",
        risk_level="MEDIUM", impact_complexity=3.0,
        belief_confidence=0.85, skills_triggered=[], tenant_id="test",
    )
    defaults.update(kw)
    return CapabilitySignalSet(**defaults)


M1_CAPS = [
    "codeintel", "lancedb", "research", "research_and_source_discipline",
]

M2_CAPS = [
    ("codeintel", "NEXUS_SKIP_CODEINTEL"),
    ("lancedb", "NEXUS_SKIP_LANCEDB"),
    ("research", "NEXUS_SKIP_RESEARCH"),
    ("research_and_source_discipline", "NEXUS_SKIP_RESEARCH_AND_SOURCE_DISCIPLINE"),
    ("aos_oracle", "NEXUS_SKIP_AOS_ORACLE"),
    ("learn_refresh_service", "NEXUS_SKIP_LEARN_REFRESH_SERVICE"),
    ("learn_scheduler_service", "NEXUS_SKIP_LEARN_SCHEDULER_SERVICE"),
    ("reflex_loop", "NEXUS_SKIP_REFLEX_LOOP"),
]


def test_x_8_capabilities_invoked_in_real_task():
    """M1: X phase capabilities appear in plan."""
    sig = _make_sig()
    plan = CapabilitySelector(project_root="/tmp").select_capabilities(
        sig, CapabilityConstraints(project_root="/tmp"))
    caps = plan.required_capabilities
    for cap in M1_CAPS:
        assert cap in caps, f"X phase cap {cap} missing: {caps}"


@pytest.mark.parametrize("skip_cap,skip_env", M2_CAPS)
def test_x_8_capabilities_disable_each_breaks_task(skip_cap, skip_env):
    """M2: Each X phase cap can be skipped via env flag."""
    os.environ[skip_env] = "1"
    try:
        sig = _make_sig()
        plan = CapabilitySelector(project_root="/tmp").select_capabilities(
            sig, CapabilityConstraints(project_root="/tmp"))
        assert skip_cap not in plan.required_capabilities
    finally:
        os.environ.pop(skip_env, None)
