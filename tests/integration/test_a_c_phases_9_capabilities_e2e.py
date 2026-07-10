from __future__ import annotations

import os

import pytest

from nexus.core.capability_selector import CapabilitySelector, CapabilityConstraints
from nexus.core.capability_signal_set import CapabilitySignalSet


def _make_sig(**kw):
    defaults = dict(
        task_id="test-e2e-ac", task_desc="audit claim closure after repair",
        risk_level="CRITICAL", impact_complexity=4.5,
        belief_confidence=0.5, skills_triggered=[], tenant_id="test",
    )
    defaults.update(kw)
    return CapabilitySignalSet(**defaults)


M1_CAPS = [
    "artifact_gate", "claim_gate", "ultra_review",
    "learning_closure", "metabolism_resume",
    "mfp_gate", "promotion_engine", "subagent_outcome_service",
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


def test_a_c_9_capabilities_invoked_in_real_task():
    """M1: A+C phase 9 capabilities appear in plan."""
    sig = _make_sig()
    plan = CapabilitySelector(project_root="/tmp").select_capabilities(
        sig, CapabilityConstraints(project_root="/tmp"))
    caps = plan.required_capabilities
    for cap in M1_CAPS:
        assert cap in caps, f"A+C cap {cap} missing: {caps}"


@pytest.mark.parametrize("skip_cap,skip_env", M2_CAPS)
def test_a_c_9_capabilities_disable_each_breaks_task(skip_cap, skip_env):
    """M2: Each A+C phase cap can be skipped via env flag."""
    os.environ[skip_env] = "1"
    try:
        sig = _make_sig()
        plan = CapabilitySelector(project_root="/tmp").select_capabilities(
            sig, CapabilityConstraints(project_root="/tmp"))
        assert skip_cap not in plan.required_capabilities
    finally:
        os.environ.pop(skip_env, None)
