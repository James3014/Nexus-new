from __future__ import annotations

import pytest

from nexus.contracts.hybrid_route import HybridRouteDecision, RouteMode


def test_hybrid_route_default_values() -> None:
    decision = HybridRouteDecision()
    assert decision.route_mode == RouteMode.CLOUD_ASSISTED_BY_LOCAL_TRACE_ONLY
    assert decision.public_claim_allowed is False
    assert decision.production_ready is False
    assert decision.adapter_output_is_route_truth is False
    assert decision.route_truth_source == "CapabilityPlanner"
    assert decision.local_guard == {}
    assert decision.behavior_changed is False
    assert decision.authority == ""
    assert decision.cloud_model_called is False
    assert decision.local_model_called is False
    assert decision.candidate_output_isolated is True
    assert decision.verifier_result == "not_run"
    assert decision.evidence_refs == ()
    assert decision.fallback_block_reason == ""


def test_hybrid_route_invalid_source_fails() -> None:
    with pytest.raises(ValueError, match="route_truth_source must be 'CapabilityPlanner'"):
        HybridRouteDecision(route_truth_source="InvalidSource")


def test_hybrid_route_public_claim_allowed_fails() -> None:
    with pytest.raises(ValueError, match="public_claim_allowed=True is forbidden"):
        HybridRouteDecision(public_claim_allowed=True)


def test_hybrid_route_local_only_executed_success() -> None:
    # 滿足條件：verifier_result != "not_run", evidence_refs 非空, candidate_output_isolated=True
    decision = HybridRouteDecision(
        route_mode=RouteMode.LOCAL_ONLY_EXECUTED,
        verifier_result="pass",
        evidence_refs=("evidence_1",),
        candidate_output_isolated=True,
    )
    assert decision.route_mode == RouteMode.LOCAL_ONLY_EXECUTED


def test_hybrid_route_local_only_executed_missing_verifier_fails() -> None:
    with pytest.raises(ValueError, match="local_only_executed requires verifier_result"):
        HybridRouteDecision(
            route_mode=RouteMode.LOCAL_ONLY_EXECUTED,
            verifier_result="not_run",  # 無效 verifier
            evidence_refs=("evidence_1",),
            candidate_output_isolated=True,
        )


def test_hybrid_route_local_only_executed_missing_evidence_fails() -> None:
    with pytest.raises(ValueError, match="local_only_executed requires verifier_result"):
        HybridRouteDecision(
            route_mode=RouteMode.LOCAL_ONLY_EXECUTED,
            verifier_result="pass",
            evidence_refs=(),  # 空 evidence_refs
            candidate_output_isolated=True,
        )


def test_hybrid_route_local_only_executed_missing_isolation_fails() -> None:
    with pytest.raises(ValueError, match="local_only_executed requires verifier_result"):
        HybridRouteDecision(
            route_mode=RouteMode.LOCAL_ONLY_EXECUTED,
            verifier_result="pass",
            evidence_refs=("evidence_1",),
            candidate_output_isolated=False,  # 無隔離
        )
