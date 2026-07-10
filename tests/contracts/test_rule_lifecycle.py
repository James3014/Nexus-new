from __future__ import annotations

from nexus.contracts.rule_lifecycle import RuleLifecycle


def test_rule_lifecycle_default_observation():
    rl = RuleLifecycle()
    assert rl.observation == {}
    assert rl.recommendation == {}
    assert rl.active is False


def test_rule_lifecycle_recommendation_state():
    rl = RuleLifecycle(
        observation={"metric": "solve_rate", "value": 0.8},
        recommendation={"action": "promote", "confidence": 0.9},
        active=True,
    )
    assert rl.observation["metric"] == "solve_rate"
    assert rl.recommendation["action"] == "promote"
    assert rl.active is True


def test_rule_lifecycle_to_dict():
    rl = RuleLifecycle(
        observation={"o": 1},
        recommendation={"r": 2},
        active=True,
    )
    d = rl.to_dict()
    assert d["observation"]["o"] == 1
    assert d["recommendation"]["r"] == 2
    assert d["active"] is True
