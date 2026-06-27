from __future__ import annotations

import pytest

from nexus.contracts.hybrid_route import (
    HybridRouteDecision,
    RouteMode,
    VerifierResult,
    Authority,
    hybrid_route_decision_from_payload,
    build_hybrid_route_decision,
)


def test_hybrid_route_default_values() -> None:
    decision = HybridRouteDecision()
    assert decision.route_mode == RouteMode.CLOUD_ASSISTED_BY_LOCAL_TRACE_ONLY
    assert decision.public_claim_allowed is False
    assert decision.production_ready is False
    assert decision.adapter_output_is_route_truth is False
    assert decision.route_truth_source == "CapabilityPlanner"
    assert decision.local_guard == {}
    assert decision.behavior_changed is False
    assert decision.authority == Authority.TRACE_ONLY
    assert decision.cloud_model_called is False
    assert decision.local_model_called is False
    assert decision.candidate_output_isolated is True
    assert decision.selected_candidate_hash == ""
    assert decision.applied_patch_hash == ""
    assert decision.selected_candidate_hash_matches_applied is False
    assert decision.verifier_result == VerifierResult.NOT_RUN
    assert decision.evidence_refs == ()
    assert decision.fallback_block_reason == ""


def test_to_dict_round_trip() -> None:
    decision = HybridRouteDecision()
    payload = decision.to_dict()
    assert payload["route_mode"] == "cloud_assisted_by_local_trace_only"
    assert payload["authority"] == "trace_only"
    assert payload["verifier_result"] == "not_run"

    round_trip = hybrid_route_decision_from_payload(payload)
    assert round_trip == decision


def test_from_payload_coerces_enum() -> None:
    payload = {
        "route_mode": "cloud_first_local_guard_advisory",
        "authority": "advisory_only",
        "verifier_result": "fail",
    }
    decision = hybrid_route_decision_from_payload(payload)
    assert decision.route_mode == RouteMode.CLOUD_FIRST_LOCAL_GUARD_ADVISORY
    assert decision.authority == Authority.ADVISORY_ONLY
    assert decision.verifier_result == VerifierResult.FAIL


def test_invalid_verifier_result_fails() -> None:
    with pytest.raises(ValueError, match="invalid_verifier_result"):
        build_hybrid_route_decision(verifier_result="invalid_res")


def test_production_ready_true_fails() -> None:
    with pytest.raises(ValueError, match="production_ready_must_be_false"):
        build_hybrid_route_decision(production_ready=True)


def test_adapter_output_is_route_truth_true_fails() -> None:
    with pytest.raises(ValueError, match="adapter_output_is_route_truth_must_be_false"):
        build_hybrid_route_decision(adapter_output_is_route_truth=True)


def test_local_only_executed_requires_hash_match() -> None:
    with pytest.raises(ValueError, match="local_only_executed_requires_hash_match"):
        HybridRouteDecision(
            route_mode=RouteMode.LOCAL_ONLY_EXECUTED,
            local_model_called=True,
            verifier_result=VerifierResult.PASS,
            evidence_refs=("ref1",),
            candidate_output_isolated=True,
            selected_candidate_hash="hash1",
            applied_patch_hash="hash1",
            selected_candidate_hash_matches_applied=False,
        )


def test_trace_only_requires_behavior_unchanged() -> None:
    with pytest.raises(ValueError, match="trace_only_requires_behavior_unchanged"):
        HybridRouteDecision(
            route_mode=RouteMode.CLOUD_ASSISTED_BY_LOCAL_TRACE_ONLY,
            behavior_changed=True,
        )


def test_advisory_guard_cannot_block_delivery_yet() -> None:
    decision = HybridRouteDecision(
        route_mode=RouteMode.CLOUD_FIRST_LOCAL_GUARD_ADVISORY,
        authority=Authority.ADVISORY_ONLY,
        verifier_result=VerifierResult.FAIL,
        behavior_changed=False,
    )
    assert decision.route_mode == RouteMode.CLOUD_FIRST_LOCAL_GUARD_ADVISORY
