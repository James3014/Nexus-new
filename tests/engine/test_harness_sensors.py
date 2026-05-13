from __future__ import annotations

from nexus.engine.harness_sensors import (
    build_bdd_acceptance_receipt,
    build_harness_preflight_sensor,
    build_sensor_fusion_decision,
    build_semantic_failure_sensor,
)


def test_harness_preflight_sensor_flags_pending_executor_and_bdd_need():
    payload = build_harness_preflight_sensor(
        task_desc="Given-When-Then business acceptance for a route change.",
        task_type="business_acceptance",
        route={"bdd_acceptance": True, "route_features": {"risk_score": 20, "candidate_count": 1}},
        pending_capabilities=("swarm",),
        selected_capabilities=("harness_preflight_sensor",),
    )

    assert payload["schema_version"] == "nexus_harness_preflight_sensor.v1"
    assert payload["capability_wired"] is False
    assert payload["executor_ready"] is False
    assert payload["bdd_acceptance_required"] is True
    assert payload["escalation_required"] is True
    assert "pending_executor_present" in payload["reasons"]


def test_semantic_failure_sensor_disallows_blind_retry():
    payload = build_semantic_failure_sensor(
        failure_text="Hidden verifier failure: AssertionError expected winner",
        phase="R",
    )

    assert payload["cause"] == "assertion_mismatch"
    assert payload["recommended_escalation"]["capabilities"] == ["autoreason"]
    assert payload["escalation_required"] is True
    assert payload["retry_policy"]["allow_blind_retry"] is False
    assert payload["retry_policy"]["requires_evidence_delta"] is True


def test_sensor_fusion_turns_failure_sensor_into_escalation_decision():
    sensor = build_semantic_failure_sensor(failure_text="Timeout while pruning candidates", phase="R")
    decision = build_sensor_fusion_decision(
        semantic_failure_sensor=sensor,
        current_route="hyper_sprint",
        phase="R",
    )

    assert decision["schema_version"] == "nexus_sensor_fusion_decision.v1"
    assert decision["escalation_required"] is True
    assert decision["recommended_route"] == "bounded_pruning"
    assert decision["recommended_capabilities"] == ["ddtree"]


def test_bdd_acceptance_receipt_requires_evidence_for_business_verified():
    verified = build_bdd_acceptance_receipt(
        given="a user has an order",
        when="they open the order detail page",
        then="the refund action is visible",
        evidence_refs=("skill://order-detail-bdd",),
    )
    technical_only = build_bdd_acceptance_receipt(
        given="a user has an order",
        when="they open the order detail page",
        then="the refund action is visible",
        evidence_refs=(),
    )

    assert verified["business_verified"] is True
    assert verified["status"] == "PASS"
    assert technical_only["business_verified"] is False
    assert technical_only["technical_verified_only"] is True
