from __future__ import annotations

import pytest

from nexus.contracts.hybrid_route import (
    Authority,
    HybridRouteDecision,
    RouteMode,
    VerifierResult,
    build_hybrid_route_decision,
    hybrid_route_decision_from_payload,
)
from nexus.engine.capability_receipt_adapters import LocalHealReceiptAdapter
from nexus.services.local_heal.hybrid_route_bridge import capability_payload_from_hybrid_route


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


def test_gb019_advisory_failure_does_not_block_delivery_or_claim() -> None:
    """GB-019: an advisory verifier failure is observational only."""
    decision = HybridRouteDecision(
        route_mode=RouteMode.CLOUD_FIRST_LOCAL_GUARD_ADVISORY,
        authority=Authority.ADVISORY_ONLY,
        verifier_result=VerifierResult.FAIL,
        evidence_refs=("gb019-evidence",),
        candidate_output_isolated=True,
    )
    payload = capability_payload_from_hybrid_route(decision)
    route_payload = payload["hybrid_route"]
    receipt = LocalHealReceiptAdapter().build(claim_verified=False, payload=payload)

    assert decision.fallback_block_reason == ""
    assert decision.blockers == ()
    assert payload["gate_passed"] is False
    assert payload["invoked"] is False
    assert route_payload["public_claim_allowed"] is False
    assert route_payload["production_ready"] is False
    assert route_payload["blockers"] == []
    assert route_payload["fallback_block_reason"] == ""
    assert receipt.gate_passed is False
    assert receipt.outcome_contributed is False
    assert receipt.public_claim_safe is False


def test_gb019_blocking_override_fails_closed() -> None:
    """A deliberate fail-closed authority is distinct from advisory mode."""
    payload = build_hybrid_route_decision(
        route_mode=RouteMode.CLOUD_FIRST_LOCAL_GUARD_FAIL_CLOSED,
        authority=Authority.FAIL_CLOSED,
        verifier_result=VerifierResult.FAIL,
        fallback_block_reason="verifier_fail",
        blockers=("verifier_fail",),
    )
    decision = hybrid_route_decision_from_payload(payload)

    assert decision.authority is Authority.FAIL_CLOSED
    assert decision.fallback_block_reason == "verifier_fail"
    assert decision.blockers == ("verifier_fail",)
    assert decision.public_claim_allowed is False


def test_public_claim_allowed_true_fails() -> None:
    with pytest.raises(ValueError, match="public_claim_allowed_must_be_false"):
        build_hybrid_route_decision(public_claim_allowed=True)


def test_route_truth_source_invalid_fails() -> None:
    with pytest.raises(ValueError, match="invalid_route_truth_source"):
        build_hybrid_route_decision(route_truth_source="InvalidSource")


def test_trace_only_rejects_behavior_changed_true() -> None:
    with pytest.raises(ValueError, match="trace_only_requires_behavior_unchanged"):
        build_hybrid_route_decision(
            route_mode=RouteMode.CLOUD_ASSISTED_BY_LOCAL_TRACE_ONLY,
            behavior_changed=True,
        )


def test_advisory_only_rejects_behavior_changed_true() -> None:
    with pytest.raises(ValueError, match="advisory_requires_behavior_unchanged"):
        build_hybrid_route_decision(
            route_mode=RouteMode.CLOUD_FIRST_LOCAL_GUARD_ADVISORY,
            behavior_changed=True,
            authority=Authority.ADVISORY_ONLY,
        )


def test_trace_only_rejects_non_trace_authority() -> None:
    with pytest.raises(ValueError, match="trace_only_requires_trace_only_authority"):
        build_hybrid_route_decision(
            route_mode=RouteMode.CLOUD_ASSISTED_BY_LOCAL_TRACE_ONLY,
            authority=Authority.ADVISORY_ONLY,
        )


def test_advisory_only_rejects_non_advisory_authority() -> None:
    with pytest.raises(ValueError, match="advisory_requires_advisory_only_authority"):
        build_hybrid_route_decision(
            route_mode=RouteMode.CLOUD_FIRST_LOCAL_GUARD_ADVISORY,
            authority=Authority.TRACE_ONLY,
        )


def test_local_only_executed_rejects_hash_mismatch() -> None:
    with pytest.raises(ValueError, match="local_only_executed_requires_hash_match"):
        build_hybrid_route_decision(
            route_mode=RouteMode.LOCAL_ONLY_EXECUTED,
            local_model_called=True,
            verifier_result=VerifierResult.PASS,
            evidence_refs=("ref1",),
            candidate_output_isolated=True,
            selected_candidate_hash="hash1",
            applied_patch_hash="hash2",
            selected_candidate_hash_matches_applied=False,
        )


def test_local_only_executed_missing_fields_fails() -> None:
    # 1. missing local_model_called (False)
    with pytest.raises(ValueError, match="local_only_executed_requires_local_model_called"):
        build_hybrid_route_decision(
            route_mode=RouteMode.LOCAL_ONLY_EXECUTED,
            local_model_called=False,
            verifier_result=VerifierResult.PASS,
            evidence_refs=("ref1",),
            candidate_output_isolated=True,
            selected_candidate_hash="hash1",
            applied_patch_hash="hash1",
            selected_candidate_hash_matches_applied=True,
        )
    # 2. missing verifier pass
    with pytest.raises(ValueError, match="local_only_executed_requires_verifier_pass"):
        build_hybrid_route_decision(
            route_mode=RouteMode.LOCAL_ONLY_EXECUTED,
            local_model_called=True,
            verifier_result=VerifierResult.NOT_RUN,
            evidence_refs=("ref1",),
            candidate_output_isolated=True,
            selected_candidate_hash="hash1",
            applied_patch_hash="hash1",
            selected_candidate_hash_matches_applied=True,
        )
    # 3. missing evidence_refs
    with pytest.raises(ValueError, match="local_only_executed_requires_evidence_refs"):
        build_hybrid_route_decision(
            route_mode=RouteMode.LOCAL_ONLY_EXECUTED,
            local_model_called=True,
            verifier_result=VerifierResult.PASS,
            evidence_refs=(),
            candidate_output_isolated=True,
            selected_candidate_hash="hash1",
            applied_patch_hash="hash1",
            selected_candidate_hash_matches_applied=True,
        )
    # 4. missing candidate_output_isolated (False)
    with pytest.raises(ValueError, match="local_only_executed_requires_candidate_output_isolated"):
        build_hybrid_route_decision(
            route_mode=RouteMode.LOCAL_ONLY_EXECUTED,
            local_model_called=True,
            verifier_result=VerifierResult.PASS,
            evidence_refs=("ref1",),
            candidate_output_isolated=False,
            selected_candidate_hash="hash1",
            applied_patch_hash="hash1",
            selected_candidate_hash_matches_applied=True,
        )
    # 5. missing selected_candidate_hash
    with pytest.raises(ValueError, match="local_only_executed_requires_selected_candidate_hash"):
        build_hybrid_route_decision(
            route_mode=RouteMode.LOCAL_ONLY_EXECUTED,
            local_model_called=True,
            verifier_result=VerifierResult.PASS,
            evidence_refs=("ref1",),
            candidate_output_isolated=True,
            selected_candidate_hash="",
            applied_patch_hash="hash1",
            selected_candidate_hash_matches_applied=True,
        )
    # 6. missing applied_patch_hash
    with pytest.raises(ValueError, match="local_only_executed_requires_applied_patch_hash"):
        build_hybrid_route_decision(
            route_mode=RouteMode.LOCAL_ONLY_EXECUTED,
            local_model_called=True,
            verifier_result=VerifierResult.PASS,
            evidence_refs=("ref1",),
            candidate_output_isolated=True,
            selected_candidate_hash="hash1",
            applied_patch_hash="",
            selected_candidate_hash_matches_applied=True,
        )
