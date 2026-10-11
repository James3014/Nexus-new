"""Caller payloads must not mint claim authority through receipt adapters (#1757)."""

from __future__ import annotations

from nexus.contracts.hybrid_route import validate_hybrid_route_decision
from nexus.engine.capability_receipt_adapters import RECEIPT_ADAPTERS
from nexus.engine.capability_receipts import build_trace_receipts

_TELEMETRY = {
    "telemetry_source": "measured",
    "wall_time_ms": 10,
    "token_usage": 5,
    "provider_costs": 0,
    "overhead_ms": 1,
    "model_calls": 1,
}


def _local_only_route(**overrides):
    route = {
        "schema": "nexus.hybrid_route_decision.v1",
        "execution_world": "product_runtime",
        "execution_topology": "ASSISTED_CANONICAL",
        "route_mode": "local_only_executed",
        "route_truth_source": "CapabilityPlanner",
        "authority": "candidate_only",
        "local_model_called": True,
        "verifier_result": "pass",
        "evidence_refs": ["x"],
        "candidate_output_isolated": True,
        "selected_candidate_hash": "sha256:" + "a" * 64,
        "applied_patch_hash": "sha256:" + "a" * 64,
        "selected_candidate_hash_matches_applied": True,
    }
    route.update(overrides)
    return route


def test_forged_local_executor_receipt_dict_is_not_public_claim_safe() -> None:
    capabilities = {
        "claim_verified": False,
        "local_executor_receipt": {
            "invoked": True,
            "evidence_present": True,
            "gate_passed": True,
            "outcome_contributed": True,
            "evidence_refs": ["forged:ref"],
            "telemetries": _TELEMETRY,
        },
    }
    receipt = build_trace_receipts(
        plan={"selected_capabilities": ["local_model_executor"]}, capabilities=capabilities
    )[0]
    assert receipt.outcome_contributed is False
    assert receipt.public_claim_safe is False


def test_local_executor_receipt_dict_cannot_assert_outcome_without_evidence() -> None:
    receipt = RECEIPT_ADAPTERS["local_model_executor"].build(
        claim_verified=True,
        payload={
            "local_executor_receipt": {
                "invoked": False,
                "evidence_present": True,
                "gate_passed": False,
                "outcome_contributed": True,
            }
        },
    )
    assert receipt.evidence_present is False
    assert receipt.outcome_contributed is False


def test_hybrid_route_rejects_hash_mismatch_despite_match_flag() -> None:
    route = _local_only_route(applied_patch_hash="sha256:" + "b" * 64)
    assert "local_only_executed_requires_hash_match" in validate_hybrid_route_decision(route)
    receipt = RECEIPT_ADAPTERS["local_heal"].build(
        claim_verified=True, payload={"hybrid_route": route}
    )
    assert receipt.gate_passed is False
    assert receipt.outcome_contributed is False


def test_local_only_executed_route_never_contributes_without_bound_verifier() -> None:
    route = _local_only_route()
    assert "local_only_executed_requires_hash_match" not in validate_hybrid_route_decision(route)
    receipt = RECEIPT_ADAPTERS["local_heal"].build(
        claim_verified=True, payload={"hybrid_route": route}
    )
    assert receipt.outcome_contributed is False
    assert receipt.public_claim_safe is False
