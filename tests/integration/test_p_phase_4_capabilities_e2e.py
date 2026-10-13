from __future__ import annotations


import pytest

from nexus.core.capability_signal_set import CapabilitySignalSet
from tests.integration.capability_plan_contract import (
    assert_planner_selection,
    assert_skip_env_is_inert,
)


def _make_sig(**kw):
    defaults = dict(
        task_id="test-e2e-p",
        task_desc="apply formula rule for high impact bug",
        risk_level="HIGH",
        impact_complexity=3.5,
        belief_confidence=0.7,
        skills_triggered=[],
        tenant_id="test",
    )
    defaults.update(kw)
    return CapabilitySignalSet(**defaults)


@pytest.mark.parametrize(
    "skip_cap,skip_env",
    [
        ("autonomic_router", "NEXUS_SKIP_AUTONOMIC_ROUTER"),
        ("predictive_auditor", "NEXUS_SKIP_PREDICTIVE_AUDITOR"),
        ("spec_guarded", "NEXUS_SKIP_SPEC_GUARDED"),
        ("decision_formula_engine", "NEXUS_SKIP_DECISION_FORMULA_ENGINE"),
    ],
)
def test_p_4_capabilities_disable_each_breaks_task(skip_cap, skip_env, monkeypatch, tmp_path):
    """Contract: NEXUS_SKIP_* no longer changes the planner's selection (#514); the planner decides."""
    assert_skip_env_is_inert(
        _make_sig(), skip_env, monkeypatch=monkeypatch, project_root=str(tmp_path)
    )


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


def test_p_4_capabilities_invoked_in_real_task(monkeypatch, tmp_path):
    """Contract: the planner's selection for this task is exactly the planned set, and it is what runs."""
    assert_planner_selection(
        _make_sig(),
        EXPECTED_PLAN,
        absent=("autonomic_router", "predictive_auditor", "spec_guarded"),
        monkeypatch=monkeypatch,
        project_root=str(tmp_path),
    )
