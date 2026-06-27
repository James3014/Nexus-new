from __future__ import annotations

from nexus.contracts.hybrid_route import RouteMode, Authority
from nexus.services.local_heal.local_solve_dry_run_loop import (
    LocalSolveDryRunRequest,
    run_local_solve_dry_run_loop,
)


def test_solve_dry_run_loop_blocked() -> None:
    req = LocalSolveDryRunRequest(
        task_id="t1",
        problem_statement="fix a bug",
        evidence_refs=("ref1",),
        model_output="```diff\n--- a/f.py\n+++ b/f.py\n-print()\n+print(1)\n```",
        verifier_result="pass",
        local_model_called=True,
        mutation_allowed=True,
    )
    
    resp = run_local_solve_dry_run_loop(req)
    assert resp.patch_envelope.parser_status == "pass"
    assert resp.apply_receipt.patch_apply_status == "blocked"
    assert resp.hybrid_route.route_mode == RouteMode.LOCAL_ONLY_BLOCKED
    assert resp.capability_payload["gate_passed"] is False


def test_solve_dry_run_loop_success() -> None:
    req = LocalSolveDryRunRequest(
        task_id="t2",
        problem_statement="fix a bug",
        evidence_refs=("ref1",),
        model_output="```diff\n--- a/f.py\n+++ b/f.py\n-print()\n+print(1)\n```",
        verifier_result="pass",
        local_model_called=True,
        mutation_allowed=True,
    )
    
    def my_apply(env) -> str:
        return env.unified_diff
        
    resp = run_local_solve_dry_run_loop(req, apply_fn=my_apply)
    assert resp.patch_envelope.parser_status == "pass"
    assert resp.apply_receipt.patch_apply_status == "applied"
    assert resp.apply_receipt.selected_candidate_hash_matches_applied is True
    assert resp.hybrid_route.route_mode == RouteMode.LOCAL_ONLY_EXECUTED
    assert resp.hybrid_route.authority == Authority.INTERNAL_ONLY
    assert resp.hybrid_route.public_claim_allowed is False
    assert resp.hybrid_route.production_ready is False
    assert resp.capability_payload["gate_passed"] is True


def test_solve_dry_run_loop_blocked_due_to_local_model_not_called() -> None:
    req = LocalSolveDryRunRequest(
        task_id="t3",
        problem_statement="fix a bug",
        evidence_refs=("ref1",),
        model_output="```diff\n--- a/f.py\n+++ b/f.py\n-print()\n+print(1)\n```",
        verifier_result="pass",
        local_model_called=False,
        mutation_allowed=True,
    )
    
    def my_apply(env) -> str:
        return env.unified_diff
        
    resp = run_local_solve_dry_run_loop(req, apply_fn=my_apply)
    assert resp.hybrid_route.route_mode == RouteMode.LOCAL_ONLY_BLOCKED
    assert "local_model_not_called" in resp.hybrid_route.fallback_block_reason
    assert resp.capability_payload["gate_passed"] is False


def test_solve_dry_run_loop_blocked_due_to_mutation_not_allowed() -> None:
    req = LocalSolveDryRunRequest(
        task_id="t4",
        problem_statement="fix a bug",
        evidence_refs=("ref1",),
        model_output="```diff\n--- a/f.py\n+++ b/f.py\n-print()\n+print(1)\n```",
        verifier_result="pass",
        local_model_called=True,
        mutation_allowed=False,
    )
    
    def my_apply(env) -> str:
        return env.unified_diff
        
    resp = run_local_solve_dry_run_loop(req, apply_fn=my_apply)
    assert resp.hybrid_route.route_mode == RouteMode.LOCAL_ONLY_BLOCKED
    assert "mutation_not_allowed" in resp.hybrid_route.fallback_block_reason
    assert resp.capability_payload["gate_passed"] is False
