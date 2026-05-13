from __future__ import annotations

from nexus.engine.harness_route_policy import (
    apply_harness_cost_lane_policy,
    apply_harness_relevance_policy,
    apply_harness_sensor_policy,
)


def test_harness_route_policy_lite_lane_downgrades_high_cost_but_keeps_governance():
    states = {
        "research": "conditional",
        "swarm": "conditional",
        "artifact_gate": "required",
        "claim_gate": "required",
        "delivery_gate": "required",
        "harness_preflight_sensor": "required",
    }
    reasons = {name: [] for name in states}

    policy = apply_harness_cost_lane_policy(
        states=states,
        reasons=reasons,
        route={"route_features": {"simple_hidden_bugfix": True, "risk_score": 10, "candidate_count": 1}},
        task_desc="Fix simple hidden bug",
        task_type="repair",
        routing_tier="L0_micro_patch",
    )

    assert policy["cost_lane"] == "lite"
    assert {"research", "swarm"} <= set(policy["downgraded"])
    assert states["research"] == "optional"
    assert states["swarm"] == "optional"
    assert states["artifact_gate"] == "required"
    assert states["claim_gate"] == "required"
    assert states["delivery_gate"] == "required"


def test_harness_route_policy_preserves_route_oracle_expected_capability():
    states = {
        "research": "conditional",
        "swarm": "conditional",
        "harness_preflight_sensor": "required",
    }
    reasons = {name: [] for name in states}

    policy = apply_harness_cost_lane_policy(
        states=states,
        reasons=reasons,
        route={"route_features": {"simple_hidden_bugfix": True, "risk_score": 10, "candidate_count": 1}},
        task_desc="Fix simple hidden bug",
        task_type="repair",
        routing_tier="L0_micro_patch",
        route_oracle_expected_capabilities=("swarm",),
    )

    assert "research" in policy["downgraded"]
    assert "swarm" not in policy["downgraded"]
    assert states["research"] == "optional"
    assert states["swarm"] == "conditional"


def test_harness_route_policy_adds_bdd_and_semantic_failure_sensors():
    states = {
        "bdd_acceptance_skill": "optional",
        "semantic_failure_sensor": "optional",
    }
    reasons = {name: [] for name in states}

    apply_harness_sensor_policy(
        states=states,
        reasons=reasons,
        route={"bdd_acceptance": True, "failure_text": "AssertionError: mismatch"},
        task_desc="Given-When-Then hidden verifier failure",
    )

    assert states["bdd_acceptance_skill"] == "conditional"
    assert states["semantic_failure_sensor"] == "conditional"


def test_harness_relevance_policy_drops_unbacked_validation_sensors():
    states = {
        "bdd_acceptance_skill": "conditional",
        "semantic_failure_sensor": "conditional",
        "artifact_gate": "required",
        "claim_gate": "required",
        "delivery_gate": "required",
    }
    reasons = {name: [] for name in states}

    policy = apply_harness_relevance_policy(
        states=states,
        reasons=reasons,
        route={"route_features": {"risk_score": 75}},
        task_desc="Accept a swarm review only when independent roles provide evidence.",
    )

    assert policy["applied"] is True
    assert set(policy["downgraded"]) == {"bdd_acceptance_skill", "semantic_failure_sensor"}
    assert states["bdd_acceptance_skill"] == "optional"
    assert states["semantic_failure_sensor"] == "optional"
    assert states["artifact_gate"] == "required"
    assert states["claim_gate"] == "required"
    assert states["delivery_gate"] == "required"


def test_harness_relevance_policy_preserves_explicit_contracts():
    states = {
        "bdd_acceptance_skill": "conditional",
        "semantic_failure_sensor": "conditional",
    }
    reasons = {name: [] for name in states}

    policy = apply_harness_relevance_policy(
        states=states,
        reasons=reasons,
        route={"failure_text": "AssertionError: hidden verifier failed"},
        task_desc="Given a verified artifact When Nexus closes Then business acceptance has evidence.",
    )

    assert policy["applied"] is False
    assert states["bdd_acceptance_skill"] == "conditional"
    assert states["semantic_failure_sensor"] == "conditional"
