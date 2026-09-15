from __future__ import annotations

from nexus.engine.planner.responsibility import (
    HARD_OBLIGATIONS,
    PLANNER_AUTHORITY_OWNER,
    PLANNER_RESPONSIBILITY_SCHEMA,
    SOFT_STRATEGIES,
    planner_responsibility_contract,
)


def test_planner_responsibility_contract_separates_hard_and_soft_dimensions():
    contract = planner_responsibility_contract()
    payload = contract.to_dict()

    assert payload["schema"] == PLANNER_RESPONSIBILITY_SCHEMA
    assert payload["authority_owner"] == PLANNER_AUTHORITY_OWNER == "James3014/Nexus-new"
    assert payload["soft_may_override_hard"] is False
    assert payload["selection_behavior_changed"] is False
    assert set(HARD_OBLIGATIONS).isdisjoint(SOFT_STRATEGIES)


def test_hard_obligations_cover_authority_evidence_verification_and_retry_safety():
    required = {
        "authority_constraints",
        "resource_effect_and_path_scope",
        "required_evidence",
        "required_verifiers",
        "stop_conditions",
        "replan_authorization",
        "effect_identity_and_retry_constraints",
    }

    assert required.issubset(HARD_OBLIGATIONS)


def test_soft_strategies_are_cognitive_choices_not_authority():
    expected = {
        "task_decomposition",
        "multi_agent_or_swarm_topology",
        "committee_or_judge_strategy",
        "research_strategy",
        "context_compression",
        "repair_strategy",
    }

    assert expected == set(SOFT_STRATEGIES)
