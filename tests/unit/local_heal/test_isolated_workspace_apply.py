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


def test_isolated_workspace_apply_metadata_diff_but_canonical_matches() -> None:
    with tempfile.TemporaryDirectory() as src_root:
        test_file = "f.py"
        src_path = os.path.join(src_root, test_file)

        with open(src_path, "w", encoding="utf-8") as f:
            f.write("print('hello')\n")

        # Unified diff without git headers
        diff_no_header = """--- a/f.py
+++ b/f.py
@@ -1 +1 @@
-print('hello')
+print('world')
"""
        # Let's calculate the hash of canonicalized diff_no_header
        # In isolated_workspace_apply, selected_candidate_hash will be compared against the canonicalized version of actual_diff
        # Let's import the normalizer or calculate it manually
        import re
        def canonicalize_diff(diff_text: str) -> str:
            lines = []
            raw_lines = diff_text.replace("\r\n", "\n").split("\n")
            for line in raw_lines:
                line_rstrip = line.rstrip()
                if line_rstrip.startswith(("diff --git", "index ", "--- ", "+++ ", "new file", "deleted file")):
                    continue
                if line_rstrip.startswith("@@"):
                    m = re.match(r"^(@@\s+-\d+(?:,\d+)?\s+\+\d+(?:,\d+)?\s+@@)", line_rstrip)
                    if m:
                        lines.append(m.group(1))
                    continue
                if line_rstrip.startswith(("-", "+", " ")):
                    op = line_rstrip[0]
                    content = line[1:].rstrip()
                    lines.append(f"{op}{content}")
                    continue
            return "\n".join(lines).strip()

        canon = canonicalize_diff(diff_no_header)
        canon_hash = hashlib.sha256(canon.encode("utf-8")).hexdigest()

        request = IsolatedApplyRequest(
            task_id="t5",
            source_root=src_root,
            target_file=test_file,
            unified_diff=diff_no_header,
            selected_candidate_hash=canon_hash,
            mutation_allowed=True,
        )

        receipt = run_isolated_workspace_apply(request)
        assert receipt.patch_apply_status == "applied"
        assert receipt.selected_candidate_hash_matches_applied is True

        # Clean up
        if os.path.exists(receipt.workspace_path):
            shutil.rmtree(receipt.workspace_path)

        # Verification of strict formatting invariants (Commit 2 check)
        # 1. Indentation mismatch check
        diff_with_indent = "@@ -1 +1 @@\n-print('hello')\n+  print('world')\n"
        diff_no_indent = "@@ -1 +1 @@\n-print('hello')\n+print('world')\n"
        assert canonicalize_diff(diff_with_indent) != canonicalize_diff(diff_no_indent)

        # 2. String literal space mismatch check
        diff_with_double_space = "@@ -1 +1 @@\n-print('hello')\n+print('world  space')\n"
        diff_with_single_space = "@@ -1 +1 @@\n-print('hello')\n+print('world space')\n"
        assert canonicalize_diff(diff_with_double_space) != canonicalize_diff(diff_with_single_space)

        # 3. Newline blank lines check
        diff_with_blank_line = "@@ -1 +1 @@\n-print('hello')\n+\n+print('world')\n"
        diff_without_blank_line = "@@ -1 +1 @@\n-print('hello')\n+print('world')\n"
        assert canonicalize_diff(diff_with_blank_line) != canonicalize_diff(diff_without_blank_line)
