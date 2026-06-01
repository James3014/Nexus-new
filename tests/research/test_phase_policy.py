import pytest
from nexus.research.learn.phase_policy import derive_phase_actions, AuditStrictness

def test_policy_allow_research_when_ready():
    summary = {"overall_pass_rate": 0.85}
    actions = derive_phase_actions(summary, "bug", "standard")
    assert actions.allow_research is True
    assert actions.force_baseline is False

def test_policy_force_baseline_when_not_ready():
    summary = {"overall_pass_rate": 0.5}
    actions = derive_phase_actions(summary, "bug", "standard")
    assert actions.allow_research is False
    assert actions.force_baseline is True

def test_policy_allow_research_for_high_risk_regardless_of_ready():
    summary = {"overall_pass_rate": 0.3}
    actions = derive_phase_actions(summary, "bug", "high")
    assert actions.allow_research is True
    assert actions.audit_strictness == AuditStrictness.STRICT
