from __future__ import annotations

import hashlib
import os
import shutil
import tempfile

from nexus.contracts.hybrid_route import RouteMode, Authority
from nexus.services.local_heal.isolated_local_solve_loop import (
    IsolatedLocalSolveRequest,
    run_isolated_local_solve_loop,
)


def test_isolated_local_solve_loop_blocked() -> None:
    req = IsolatedLocalSolveRequest(
        task_id="t1",
        source_root=".",
        problem_statement="fix code",
        evidence_refs=("ref1",),
        model_output="```diff\n--- a/f.py\n+++ b/f.py\n-print()\n+print(1)\n```",
        verifier_command=("python3", "-c", "import sys; sys.exit(0)"),
        local_model_called=True,
        mutation_allowed=False,
        verifier_allowed=True,
    )
    resp = run_isolated_local_solve_loop(req)
    assert resp.hybrid_route.route_mode == RouteMode.LOCAL_ONLY_BLOCKED
    assert "mutation_not_allowed" in resp.hybrid_route.fallback_block_reason


def test_isolated_local_solve_loop_success() -> None:
    with tempfile.TemporaryDirectory() as src_root:
        test_file = "f.py"
        src_path = os.path.join(src_root, test_file)
        with open(src_path, "w", encoding="utf-8") as f:
            f.write("print('hello')\n")
            
        diff = """--- a/f.py
+++ b/f.py
@@ -1 +1 @@
-print('hello')
+print('world')
"""
        req = IsolatedLocalSolveRequest(
            task_id="t2",
            source_root=src_root,
            problem_statement="fix code",
            evidence_refs=("ref1",),
            model_output=f"```diff\n{diff}```",
            verifier_command=("python3", "-c", "import os; assert os.path.exists('f.py'); f=open('f.py'); assert 'world' in f.read()"),
            local_model_called=True,
            mutation_allowed=True,
            verifier_allowed=True,
        )
        
        resp = run_isolated_local_solve_loop(req)
        assert resp.patch_envelope.parser_status == "pass"
        assert resp.apply_receipt.patch_apply_status == "applied"
        assert resp.apply_receipt.applied_patch_hash_source == "git_diff"
        assert resp.apply_receipt.selected_candidate_hash_matches_applied is True
        assert resp.verifier_receipt.verifier_status == "pass"
        
        assert resp.hybrid_route.route_mode == RouteMode.LOCAL_ONLY_EXECUTED
        assert resp.hybrid_route.authority == Authority.INTERNAL_ONLY
        assert resp.capability_payload["gate_passed"] is True
        
        assert resp.hybrid_route.public_claim_allowed is False
        assert resp.hybrid_route.production_ready is False
        
        with open(src_path, "r", encoding="utf-8") as f:
            assert f.read() == "print('hello')\n"
            
        if os.path.exists(resp.apply_receipt.workspace_path):
            shutil.rmtree(resp.apply_receipt.workspace_path)


def test_isolated_local_solve_loop_hash_mismatch_blocked() -> None:
    with tempfile.TemporaryDirectory() as src_root:
        test_file = "f.py"
        src_path = os.path.join(src_root, test_file)
        with open(src_path, "w", encoding="utf-8") as f:
            f.write("print('hello')\n")
            
        diff = """--- a/f.py
+++ b/f.py
@@ -1 +1 @@
-print('hello')
+print('world')
"""
        req = IsolatedLocalSolveRequest(
            task_id="t3",
            source_root=src_root,
            problem_statement="fix code",
            evidence_refs=("ref1",),
            model_output=f"```diff\n{diff}```",
            verifier_command=("python3", "-c", "print(1)"),
            local_model_called=True,
            mutation_allowed=True,
            verifier_allowed=True,
        )
        
        from unittest.mock import patch
        import nexus.services.local_heal.isolated_local_solve_loop as loop_module
        
        from nexus.services.local_heal.local_model_patch_envelope import parse_local_model_patch_envelope
        orig_envelope = parse_local_model_patch_envelope("t3", f"```diff\n{diff}```")
        
        from nexus.services.local_heal.local_model_patch_envelope import LocalModelPatchEnvelope
        bad_envelope = LocalModelPatchEnvelope(
            task_id=orig_envelope.task_id,
            raw_model_output=orig_envelope.raw_model_output,
            candidate_id=orig_envelope.candidate_id,
            target_file=orig_envelope.target_file,
            unified_diff=orig_envelope.unified_diff,
            parser_status=orig_envelope.parser_status,
            candidate_hash="wrong_hash_candidate",
        )
        
        with patch.object(loop_module, "parse_local_model_patch_envelope", return_value=bad_envelope):
            resp = run_isolated_local_solve_loop(req)
            
        assert resp.apply_receipt.selected_candidate_hash_matches_applied is False
        assert resp.hybrid_route.route_mode == RouteMode.LOCAL_ONLY_BLOCKED
        assert "hash_match_not_proven" in resp.hybrid_route.fallback_block_reason
        
        if os.path.exists(resp.apply_receipt.workspace_path):
            shutil.rmtree(resp.apply_receipt.workspace_path)
