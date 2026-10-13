from __future__ import annotations


import pytest

from nexus.core.capability_signal_set import CapabilitySignalSet
from tests.integration.capability_plan_contract import (
    assert_planner_selection,
    assert_skip_env_is_inert,
)


def _make_sig(**kw):
    defaults = dict(
        task_id="test-e2e-x",
        task_desc="research source optimize refresh schedule",
        risk_level="MEDIUM",
        impact_complexity=3.0,
        belief_confidence=0.85,
        skills_triggered=[],
        tenant_id="test",
    )
    defaults.update(kw)
    return CapabilitySignalSet(**defaults)


M1_CAPS = [
    "codeintel",
    "lancedb",
    "research",
    "research_and_source_discipline",
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

EXPECTED_PLAN = frozenset({
    "artifact_gate",
    "claim_gate",
    "codeintel",
    "mempalace",
})


def test_x_8_capabilities_invoked_in_real_task(monkeypatch, tmp_path):
    """Contract: the planner's selection for this task is exactly the planned set, and it is what runs."""
    assert_planner_selection(
        _make_sig(),
        EXPECTED_PLAN,
        absent=("lancedb", "research", "research_and_source_discipline"),
        monkeypatch=monkeypatch,
        project_root=str(tmp_path),
    )


@pytest.mark.parametrize("skip_cap,skip_env", M2_CAPS)
def test_x_8_capabilities_disable_each_breaks_task(skip_cap, skip_env, monkeypatch, tmp_path):
    """Contract: NEXUS_SKIP_* no longer changes the planner's selection (#514); the planner decides."""
    assert_skip_env_is_inert(
        _make_sig(), skip_env, monkeypatch=monkeypatch, project_root=str(tmp_path)
    )
