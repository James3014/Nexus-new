from __future__ import annotations


import pytest

from nexus.core.capability_signal_set import CapabilitySignalSet
from tests.integration.capability_plan_contract import (
    assert_planner_selection,
    assert_skip_env_is_inert,
)


def _make_sig(**kw):
    defaults = dict(
        task_id="test-e2e-ac",
        task_desc="audit claim closure after repair",
        risk_level="CRITICAL",
        impact_complexity=4.5,
        belief_confidence=0.5,
        skills_triggered=[],
        tenant_id="test",
    )
    defaults.update(kw)
    return CapabilitySignalSet(**defaults)


M1_CAPS = [
    "artifact_gate",
    "claim_gate",
    "ultra_review",
    "learning_closure",
    "metabolism_resume",
    "mfp_gate",
    "promotion_engine",
    "subagent_outcome_service",
    "attempt_settlement_service",
]

M2_CAPS = [
    ("artifact_gate", "NEXUS_SKIP_ARTIFACT_GATE"),
    ("claim_gate", "NEXUS_SKIP_CLAIM_GATE"),
    ("ultra_review", "NEXUS_SKIP_ULTRA_REVIEW"),
    ("learning_closure", "NEXUS_SKIP_LEARNING_CLOSURE"),
    ("metabolism_resume", "NEXUS_SKIP_METABOLISM_RESUME"),
    ("mfp_gate", "NEXUS_SKIP_MFP_GATE"),
    ("promotion_engine", "NEXUS_SKIP_PROMOTION_ENGINE"),
    ("subagent_outcome_service", "NEXUS_SKIP_SUBAGENT_OUTCOME_SERVICE"),
    ("attempt_settlement_service", "NEXUS_SKIP_ATTEMPT_SETTLEMENT_SERVICE"),
]

EXPECTED_PLAN = frozenset({
    "artifact_gate",
    "belief",
    "claim_gate",
    "codeintel",
    "drone",
    "forecast_pregate",
    "mempalace",
    "nightshift",
    "nightshift_runner_service",
    "repair_loop",
    "sandbox_replay",
    "sandbox_runner",
    "swarm_multi_agent",
    "ultra_review",
})


def test_a_c_9_capabilities_invoked_in_real_task(monkeypatch, tmp_path):
    """Contract: the planner's selection for this task is exactly the planned set, and it is what runs."""
    assert_planner_selection(
        _make_sig(),
        EXPECTED_PLAN,
        absent=(
            "learning_closure",
            "metabolism_resume",
            "mfp_gate",
            "promotion_engine",
            "subagent_outcome_service",
            "attempt_settlement_service",
        ),
        monkeypatch=monkeypatch,
        project_root=str(tmp_path),
    )


@pytest.mark.parametrize("skip_cap,skip_env", M2_CAPS)
def test_a_c_9_capabilities_disable_each_breaks_task(skip_cap, skip_env, monkeypatch, tmp_path):
    """Contract: NEXUS_SKIP_* no longer changes the planner's selection (#514); the planner decides."""
    assert_skip_env_is_inert(
        _make_sig(), skip_cap, skip_env, monkeypatch=monkeypatch, project_root=str(tmp_path)
    )
