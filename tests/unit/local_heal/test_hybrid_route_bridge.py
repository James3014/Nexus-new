from __future__ import annotations

import pytest

from nexus.contracts.hybrid_route import RouteMode, VerifierResult, Authority
from nexus.services.local_heal.local_model_adapter_contract import LocalModelAdapterReceipt
from nexus.services.local_heal.first_solve_harness import SolveAttemptReceipt
from nexus.services.local_heal.native_validation_bridge import ValidationReceipt
from nexus.services.local_heal.hybrid_route_bridge import (
    hybrid_route_from_local_model_receipt,
    hybrid_route_from_solve_attempt_receipt,
    hybrid_route_from_validation_receipt,
    capability_payload_from_hybrid_route,
    build_local_heal_hybrid_receipt,
)


def test_bridge_from_local_model_receipt_blocked_by_default() -> None:
    receipt = LocalModelAdapterReceipt(
        receipt_id="r1",
        request_id="req1",
        verifier_result="pass",
        evidence_refs=("ref1",),
        candidate_output_isolated=True,
        selected_candidate_hash="hash123",
        local_model_called=True,
    )
    decision = hybrid_route_from_local_model_receipt(receipt)
    assert decision.route_mode == RouteMode.LOCAL_ONLY_BLOCKED
    assert decision.authority == Authority.TRACE_ONLY
    assert "missing_applied_patch_hash" in decision.fallback_block_reason


def test_bridge_from_solve_attempt_receipt_blocked() -> None:
    receipt = SolveAttemptReceipt(
        task_id="t1",
        candidate_id="c1",
        selected_candidate_hash="hash1",
        verifier_result="pass",
        evidence_refs=("ref1",),
        local_model_called=True,
    )
    decision = hybrid_route_from_solve_attempt_receipt(receipt)
    assert decision.route_mode == RouteMode.LOCAL_ONLY_BLOCKED
    assert "missing_applied_patch_hash" in decision.fallback_block_reason


def test_bridge_from_validation_receipt_blocked() -> None:
    receipt = ValidationReceipt(
        route_id="route1",
        evidence_packet_id="ep1",
        model_role="repair",
        model_name="qwen",
        candidate_id="hash9",
        parser_status="pass",
        patch_apply_status="applied",
        verifier_status="pass",
        sandbox_status="pass",
        compliance_status="pass",
        claim_status="internal_only",
        acceptance_status="internal_only",
        final_status="VERIFIER_PASS_INTERNAL_ONLY",
        authority_trace=[],
    )
    decision = hybrid_route_from_validation_receipt(receipt)
    assert decision.route_mode == RouteMode.LOCAL_ONLY_BLOCKED
    assert "missing_applied_patch_hash" in decision.fallback_block_reason


def test_build_local_heal_hybrid_receipt_executed_when_explicit() -> None:
    decision = build_local_heal_hybrid_receipt(
        task_id="t1",
        route_mode=RouteMode.LOCAL_ONLY_EXECUTED,
        verifier_result=VerifierResult.PASS,
        evidence_refs=("ref1",),
        candidate_output_isolated=True,
        selected_candidate_hash="hash1",
        applied_patch_hash="hash1",
    )
    assert decision.route_mode == RouteMode.LOCAL_ONLY_EXECUTED
    assert decision.authority == Authority.INTERNAL_ONLY
    assert decision.selected_candidate_hash_matches_applied is True


def test_build_local_heal_hybrid_receipt_blocked_when_mismatched() -> None:
    decision = build_local_heal_hybrid_receipt(
        task_id="t1",
        route_mode=RouteMode.LOCAL_ONLY_EXECUTED,
        verifier_result=VerifierResult.PASS,
        evidence_refs=("ref1",),
        candidate_output_isolated=True,
        selected_candidate_hash="hash1",
        applied_patch_hash="hash2",
    )
    assert decision.route_mode == RouteMode.LOCAL_ONLY_BLOCKED
    assert "hash_mismatch" in decision.fallback_block_reason


def test_capability_payload_mapping() -> None:
    decision = build_local_heal_hybrid_receipt(
        task_id="t1",
        route_mode=RouteMode.LOCAL_ONLY_EXECUTED,
        verifier_result=VerifierResult.PASS,
        evidence_refs=("ref1",),
        candidate_output_isolated=True,
        selected_candidate_hash="hash1",
        applied_patch_hash="hash1",
    )
    payload = capability_payload_from_hybrid_route(decision)
    assert payload["invoked"] is True
    assert payload["gate_passed"] is True
    assert payload["evidence_present"] is True
    assert payload["evidence_refs"] == ["ref1"]
    assert payload["telemetries"]["route_mode"] == "local_only_executed"
    assert payload["telemetries"]["authority"] == "internal_only"
