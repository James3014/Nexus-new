from __future__ import annotations

from nexus.contracts.hybrid_route import RouteMode, Authority
from nexus.services.local_heal.local_solve_dry_run_loop import (
    LocalSolveDryRunRequest,
    run_local_solve_dry_run_loop,
)


def test_universal_solve_dry_run_seam_flow() -> None:
    req1 = LocalSolveDryRunRequest(
        task_id="t1",
        problem_statement="fix code",
        evidence_refs=("ref1",),
        model_output="Here is no diff text",
        verifier_result="pass",
        local_model_called=True,
        mutation_allowed=True,
    )
    resp1 = run_local_solve_dry_run_loop(req1)
    assert resp1.patch_envelope.parser_status == "blocked"
    assert resp1.hybrid_route.route_mode == RouteMode.LOCAL_ONLY_BLOCKED
    assert "missing_unified_diff" in resp1.hybrid_route.fallback_block_reason
    assert resp1.capability_payload["gate_passed"] is False
    
    req2 = LocalSolveDryRunRequest(
        task_id="t2",
        problem_statement="fix code",
        evidence_refs=("ref1",),
        model_output="```diff\n--- a/f.py\n+++ b/f.py\n-print()\n+print(1)\n```",
        verifier_result="pass",
        local_model_called=True,
        mutation_allowed=True,
    )
    resp2 = run_local_solve_dry_run_loop(req2)
    assert resp2.patch_envelope.parser_status == "pass"
    assert resp2.apply_receipt.patch_apply_status == "blocked"
    assert resp2.hybrid_route.route_mode == RouteMode.LOCAL_ONLY_BLOCKED
    assert "apply_fn_missing" in resp2.hybrid_route.fallback_block_reason
    assert resp2.capability_payload["gate_passed"] is False
    
    def bad_apply(env) -> str:
        return "completely mismatched patch text"
        
    resp3 = run_local_solve_dry_run_loop(req2, apply_fn=bad_apply)
    assert resp3.patch_envelope.parser_status == "pass"
    assert resp3.apply_receipt.patch_apply_status == "applied"
    assert resp3.apply_receipt.selected_candidate_hash_matches_applied is False
    assert resp3.hybrid_route.route_mode == RouteMode.LOCAL_ONLY_BLOCKED
    assert "hash_match_not_proven" in resp3.hybrid_route.fallback_block_reason
    assert resp3.capability_payload["gate_passed"] is False
    
    def good_apply(env) -> str:
        return env.unified_diff
        
    resp4 = run_local_solve_dry_run_loop(req2, apply_fn=good_apply)
    assert resp4.patch_envelope.parser_status == "pass"
    assert resp4.apply_receipt.patch_apply_status == "applied"
    assert resp4.apply_receipt.selected_candidate_hash_matches_applied is True
    assert resp4.hybrid_route.route_mode == RouteMode.LOCAL_ONLY_EXECUTED
    assert resp4.hybrid_route.authority == Authority.INTERNAL_ONLY
    assert resp4.capability_payload["gate_passed"] is True
    assert resp4.hybrid_route.public_claim_allowed is False
    assert resp4.hybrid_route.production_ready is False


def test_universal_solve_dry_run_seam_flow_safety_violations() -> None:
    req_base = LocalSolveDryRunRequest(
        task_id="t3",
        problem_statement="fix code",
        evidence_refs=("ref1",),
        model_output="```diff\n--- a/f.py\n+++ b/f.py\n-print()\n+print(1)\n```",
        verifier_result="pass",
    )
    
    def good_apply(env) -> str:
        return env.unified_diff

    req_no_call = LocalSolveDryRunRequest(
        task_id="t3",
        problem_statement=req_base.problem_statement,
        evidence_refs=req_base.evidence_refs,
        model_output=req_base.model_output,
        verifier_result=req_base.verifier_result,
        local_model_called=False,
        mutation_allowed=True,
    )
    resp_no_call = run_local_solve_dry_run_loop(req_no_call, apply_fn=good_apply)
    assert resp_no_call.hybrid_route.route_mode == RouteMode.LOCAL_ONLY_BLOCKED
    assert "local_model_not_called" in resp_no_call.hybrid_route.fallback_block_reason
    assert resp_no_call.capability_payload["gate_passed"] is False

    req_no_mut = LocalSolveDryRunRequest(
        task_id="t3",
        problem_statement=req_base.problem_statement,
        evidence_refs=req_base.evidence_refs,
        model_output=req_base.model_output,
        verifier_result=req_base.verifier_result,
        local_model_called=True,
        mutation_allowed=False,
    )
    resp_no_mut = run_local_solve_dry_run_loop(req_no_mut, apply_fn=good_apply)
    assert resp_no_mut.hybrid_route.route_mode == RouteMode.LOCAL_ONLY_BLOCKED
    assert "mutation_not_allowed" in resp_no_mut.hybrid_route.fallback_block_reason
    assert resp_no_mut.capability_payload["gate_passed"] is False
