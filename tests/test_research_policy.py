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


def test_route_experimental_when_workspace_available():
    policy = ResearchPolicy(fast_mode=False)
    route = policy.route(
        {"external_needed": False},
        "optimize latency for flaky api path",
        context={"research_workspace": "/tmp/demo"},
    )
    assert route.should_research is True
    assert route.mode == "experimental"
    assert route.stable_wins >= 1


def test_route_skip_for_clear_bug_without_trigger():
    policy = ResearchPolicy(fast_mode=False)
    route = policy.route(
        {"external_needed": False},
        "fix typo in docs heading",
        task_type="bug",
        prediction={"candidate_count": 1, "root_cause_confidence": 0.95},
    )
    assert route.should_research is False
    assert route.mode == "skip"
