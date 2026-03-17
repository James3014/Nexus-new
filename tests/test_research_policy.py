import pytest
from nexus.engine.policies.research_policy import ResearchPolicy

def test_should_research_true():
    policy = ResearchPolicy(fast_mode=False)
    decision = {"external_needed": True}
    assert policy.should_research(decision, "task") is True

def test_should_research_fast_mode():
    policy = ResearchPolicy(fast_mode=True)
    decision = {"external_needed": True}
    assert policy.should_research(decision, "task") is False

def test_should_research_keyword_trigger():
    policy = ResearchPolicy(fast_mode=False)
    decision = {"external_needed": False}
    assert policy.should_research(decision, "Integrate SDK with WebSocket") is True
