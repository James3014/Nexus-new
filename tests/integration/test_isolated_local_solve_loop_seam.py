from __future__ import annotations

import hashlib
import os
import shutil
import tempfile

from nexus.contracts.hybrid_route import RouteMode
from nexus.services.local_heal.isolated_local_solve_loop import (
    IsolatedLocalSolveRequest,
    run_isolated_local_solve_loop,
)


def test_isolated_local_solve_loop_seam_violations() -> None:
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
        
        req1 = IsolatedLocalSolveRequest(
            task_id="t1",
            source_root=src_root,
            problem_statement="fix code",
            evidence_refs=("ref1",),
            model_output=f"```diff\n{diff}```",
            verifier_command=("python3", "-c", "print(1)"),
            local_model_called=True,
            mutation_allowed=True,
            verifier_allowed=False,
            target_file="f.py",
        )
        resp1 = run_isolated_local_solve_loop(req1)
        assert resp1.hybrid_route.route_mode == RouteMode.LOCAL_ONLY_BLOCKED
        assert "verifier_not_allowed" in resp1.hybrid_route.fallback_block_reason
        if os.path.exists(resp1.apply_receipt.workspace_path):
            shutil.rmtree(resp1.apply_receipt.workspace_path)
            
        req2 = IsolatedLocalSolveRequest(
            task_id="t2",
            source_root=src_root,
            problem_statement="fix code",
            evidence_refs=("ref1",),
            model_output="```diff\n--- a/../outside.py\n+++ b/../outside.py\n@@ -1 +1 @@\n-1\n+2\n```",
            verifier_command=("python3", "-c", "print(1)"),
            local_model_called=True,
            mutation_allowed=True,
            verifier_allowed=True,
            target_file="f.py",
        )
        resp2 = run_isolated_local_solve_loop(req2)
        assert resp2.hybrid_route.route_mode == RouteMode.LOCAL_ONLY_BLOCKED
        assert "path_traversal_detected" in resp2.hybrid_route.fallback_block_reason
        if os.path.exists(resp2.apply_receipt.workspace_path):
            shutil.rmtree(resp2.apply_receipt.workspace_path)
            
        req3 = IsolatedLocalSolveRequest(
            task_id="t3",
            source_root=src_root,
            problem_statement="fix code",
            evidence_refs=("ref1",),
            model_output="```diff\n--- a/f.py\n+++ b/f.py\n@@ -1 +1 @@\n-wrong content\n+print('world')\n```",
            verifier_command=("python3", "-c", "print(1)"),
            local_model_called=True,
            mutation_allowed=True,
            verifier_allowed=True,
            target_file="f.py",
        )
        resp3 = run_isolated_local_solve_loop(req3)
        assert resp3.hybrid_route.route_mode == RouteMode.LOCAL_ONLY_BLOCKED
        assert "failed" in resp3.apply_receipt.patch_apply_status
        assert resp3.capability_payload["gate_passed"] is False
        if os.path.exists(resp3.apply_receipt.workspace_path):
            shutil.rmtree(resp3.apply_receipt.workspace_path)
            
        req4 = IsolatedLocalSolveRequest(
            task_id="t4",
            source_root=src_root,
            problem_statement="fix code",
            evidence_refs=("ref1",),
            model_output=f"```diff\n{diff}```",
            verifier_command=("python3", "-c", "import sys; sys.exit(9)"),
            local_model_called=True,
            mutation_allowed=True,
            verifier_allowed=True,
            target_file="f.py",
        )
        resp4 = run_isolated_local_solve_loop(req4)
        assert resp4.hybrid_route.route_mode == RouteMode.LOCAL_ONLY_BLOCKED
        assert resp4.verifier_receipt.verifier_status == "fail"
        if os.path.exists(resp4.apply_receipt.workspace_path):
            shutil.rmtree(resp4.apply_receipt.workspace_path)
