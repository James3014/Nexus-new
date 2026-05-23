from __future__ import annotations

from nexus.engine.route_cost_policy_matcher import controls_from_feature_rules, feature_rule_matches


def test_feature_rule_matches_scalar_and_list_values():
    assert feature_rule_matches(
        {"repo_kind": "neutral_fixture", "task_type": ["bug", "public_feature"]},
        {"repo_kind": "neutral_fixture", "task_type": "bug"},
    ) is True
    assert feature_rule_matches(
        {"repo_kind": "neutral_fixture", "task_type": ["bug"]},
        {"repo_kind": "external", "task_type": "bug"},
    ) is False
    assert feature_rule_matches({}, {"repo_kind": "neutral_fixture"}) is False


def test_controls_from_feature_rules_returns_first_matching_sanitized_controls():
    rules = [
        {"id": "miss", "match": {"repo_kind": "external"}, "controls": {"candidate_cap": 9}},
        {
            "id": "compact-bug",
            "match": {"repo_kind": "neutral_fixture", "task_type": ["bug", "public_feature"]},
            "controls": {
                "candidate_cap": "2",
                "lite_route": True,
                "hold": False,
                "supervised_bare_first": True,
                "allow_medium_risk_supervised_bare_first": True,
                "allow_high_risk_supervised_bare_first": True,
                "allow_pre_model_deterministic_rescue": True,
                "skip_llm_baseline": True,
                "require_llm_baseline": True,
                "disable_research": True,
                "max_rounds": "1",
                "context_mode": " compact ",
                "route_lane": "hidden_lite",
            },
        },
    ]

    controls = controls_from_feature_rules(
        rules,
        {"repo_kind": "neutral_fixture", "task_type": "bug"},
    )

    assert controls == {
        "candidate_cap": 2,
        "lite_route": True,
        "supervised_bare_first": True,
        "allow_medium_risk_supervised_bare_first": True,
        "allow_high_risk_supervised_bare_first": True,
        "allow_pre_model_deterministic_rescue": True,
        "skip_llm_baseline": True,
        "require_llm_baseline": True,
        "disable_research": True,
        "max_rounds": 1,
        "context_mode": "compact",
        "route_lane": "hidden_lite",
        "policy_source": "compact-bug",
    }


def test_controls_from_feature_rules_ignores_invalid_rules_and_non_matches():
    assert controls_from_feature_rules("not-list", {"repo_kind": "neutral_fixture"}) == {}
    assert controls_from_feature_rules([{"match": [], "controls": {}}], {"repo_kind": "neutral_fixture"}) == {}
    assert controls_from_feature_rules(
        [{"id": "miss", "match": {"repo_kind": "external"}, "controls": {"candidate_cap": 1}}],
        {"repo_kind": "neutral_fixture"},
    ) == {}
