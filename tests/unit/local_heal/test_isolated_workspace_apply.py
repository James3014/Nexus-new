from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from nexus.services.local_heal.isolated_workspace_apply import (
    IsolatedApplyRequest,
    run_isolated_workspace_apply,
)


def test_isolated_workspace_apply_blocked() -> None:
    request = IsolatedApplyRequest(
        task_id="t1",
        source_root=".",
        target_file="test.py",
        unified_diff="",
        selected_candidate_hash="",
        mutation_allowed=False,
    )
    receipt = run_isolated_workspace_apply(request)
    assert receipt.patch_apply_status == "blocked"
    assert "mutation_not_allowed" in receipt.patch_apply_error


def test_isolated_workspace_apply_traversal() -> None:
    request = IsolatedApplyRequest(
        task_id="t2",
        source_root=".",
        target_file="../outside.py",
        unified_diff="",
        selected_candidate_hash="",
        mutation_allowed=True,
    )
    receipt = run_isolated_workspace_apply(request)
    assert receipt.patch_apply_status == "blocked"
    assert "path_traversal_detected" in receipt.patch_apply_error


def test_isolated_workspace_apply_success_and_mismatch() -> None:
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
        diff_hash = hashlib.sha256(diff.strip().encode("utf-8")).hexdigest()
        
        request_match = IsolatedApplyRequest(
            task_id="t3",
            source_root=src_root,
            target_file=test_file,
            unified_diff=diff,
            selected_candidate_hash=diff_hash,
            mutation_allowed=True,
        )
        
        receipt_match = run_isolated_workspace_apply(request_match)
        assert receipt_match.patch_apply_status == "applied"
        assert receipt_match.selected_candidate_hash_matches_applied is True
        assert receipt_match.candidate_output_isolated is True
        assert receipt_match.applied_patch_hash_source == "git_diff"
        
        if os.path.exists(receipt_match.workspace_path):
            shutil.rmtree(receipt_match.workspace_path)
            
        request_mismatch = IsolatedApplyRequest(
            task_id="t4",
            source_root=src_root,
            target_file=test_file,
            unified_diff=diff,
            selected_candidate_hash="wrong_hash_provenance",
            mutation_allowed=True,
        )
        receipt_mismatch = run_isolated_workspace_apply(request_mismatch)
        assert receipt_mismatch.patch_apply_status == "applied"
        assert receipt_mismatch.selected_candidate_hash_matches_applied is False
        assert receipt_mismatch.applied_patch_hash_source == "git_diff"
        
        if os.path.exists(receipt_mismatch.workspace_path):
            shutil.rmtree(receipt_mismatch.workspace_path)
            
        with open(src_path, "r", encoding="utf-8") as f:
            assert f.read() == "print('hello')\n"
