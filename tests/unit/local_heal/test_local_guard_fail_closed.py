from __future__ import annotations

from nexus.contracts.hybrid_route import RouteMode, Authority
from nexus.services.local_heal.local_guard_fail_closed import (
    LocalGuardInput,
    run_local_guard_fail_closed,
)


def test_local_guard_fail_closed_safe() -> None:
    guard_input = LocalGuardInput(
        task_id="t1",
        route_payload={
            "public_claim_allowed": False,
            "production_ready": False,
            "adapter_output_is_route_truth": False,
            "metadata": {
                "advisory_text_hash": "hash123",
                "advisory_text_preview": "preview...",
            }
        },
        evidence_refs=("ref1",),
        verifier_result="pass",
        selected_candidate_hash="hash1",
        applied_patch_hash="hash1",
        route_truth_source="CapabilityPlanner",
    )
    decision = run_local_guard_fail_closed(guard_input)
    assert decision.guard_invoked is True
    assert decision.guard_blocked is False
    assert not decision.blockers
    assert decision.route_mode == RouteMode.CLOUD_FIRST_LOCAL_GUARD_ADVISORY
    assert decision.authority == Authority.ADVISORY_ONLY


def test_local_guard_fail_closed_violations() -> None:
    input1 = LocalGuardInput(
        task_id="t2",
        route_payload={"public_claim_allowed": True},
    )
    assert "public_claim_allowed_must_be_false" in run_local_guard_fail_closed(input1).blockers
    
    input2 = LocalGuardInput(
        task_id="t3",
        route_payload={"production_ready": True},
    )
    assert "production_ready_must_be_false" in run_local_guard_fail_closed(input2).blockers
    
    input3 = LocalGuardInput(
        task_id="t4",
        route_payload={"adapter_output_is_route_truth": True},
    )
    assert "adapter_output_is_route_truth_must_be_false" in run_local_guard_fail_closed(input3).blockers
    
    input4 = LocalGuardInput(
        task_id="t5",
        route_payload={},
        route_truth_source="attacker",
    )
    assert "invalid_route_truth_source" in run_local_guard_fail_closed(input4).blockers
    
    input5 = LocalGuardInput(
        task_id="t6",
        route_payload={},
        verifier_result="fail",
    )
    assert "verifier_fail" in run_local_guard_fail_closed(input5).blockers
    
    input6 = LocalGuardInput(
        task_id="t7",
        route_payload={},
        verifier_result="pass",
        evidence_refs=(),
    )
    assert "missing_evidence_refs" in run_local_guard_fail_closed(input6).blockers
    
    input7 = LocalGuardInput(
        task_id="t8",
        route_payload={},
        selected_candidate_hash="hash1",
        applied_patch_hash="hash2",
    )
    assert "hash_mismatch" in run_local_guard_fail_closed(input7).blockers
