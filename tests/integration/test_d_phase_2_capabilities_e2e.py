from __future__ import annotations


import pytest

from nexus.core.capability_signal_set import CapabilitySignalSet
from tests.integration.capability_plan_contract import (
    assert_planner_selection,
    assert_skip_env_is_inert,
)


def _make_sig(**kw):
    defaults = dict(
        task_id="test-e2e-d",
        task_desc="ambiguous decision needed",
        risk_level="CRITICAL",
        impact_complexity=4.0,
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


def test_d_2_capabilities_invoked_in_real_task(monkeypatch, tmp_path):
    """Contract: the planner's selection for this task is exactly the planned set, and it is what runs."""
    assert_planner_selection(
        _make_sig(),
        EXPECTED_PLAN,
        absent=(),
        monkeypatch=monkeypatch,
        project_root=str(tmp_path),
    )


@pytest.mark.parametrize(
    "skip_cap,skip_env",
    [
        ("belief", "NEXUS_SKIP_BELIEF"),
        ("autoreason", "NEXUS_SKIP_AUTOREASON"),
    ],
)
def test_d_2_capabilities_disable_each_breaks_task(skip_cap, skip_env, monkeypatch, tmp_path):
    """Contract: NEXUS_SKIP_* no longer changes the planner's selection (#514); the planner decides."""
    assert_skip_env_is_inert(
        _make_sig(), skip_env, monkeypatch=monkeypatch, project_root=str(tmp_path)
    )
