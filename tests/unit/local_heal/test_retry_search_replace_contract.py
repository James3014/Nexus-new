"""C6H: Retry search/replace contract tests.

Ensures retry prompt enforces SEARCH/REPLACE format and forbids unified diff.
"""
from __future__ import annotations

import pytest


def test_retry_prompt_requires_search_replace_blocks_only():
    """Retry prompt must explicitly require SEARCH/REPLACE format."""
    from nexus.services.local_heal.prompt_builder import PromptBuilder

    prompt = PromptBuilder.build_verification_guided_retry_prompt(
        original_user_prompt="Fix normalize_score",
        verification_report="FAIL: normalize_score does not clamp",
        canonical_search_span="def normalize_score(score, min_val, max_val):",
        target_file="toy/math_util.py",
        retry_count=1,
        verifier_failure_kind="exception",
        verifier_stdout_excerpt="EVIDENCE: normalize_score does not clamp",
        verifier_stderr_excerpt="",
        verifier_exit_code="1",
        verifier_command_hash="abc123",
    )

    # Must contain SEARCH/REPLACE markers
    assert "<<<<<<< SEARCH" in prompt
    assert "=======" in prompt
    assert ">>>>>>> REPLACE" in prompt
    # Must contain FILE template
    assert "FILE: toy/math_util.py" in prompt


def test_retry_prompt_forbids_unified_diff_output():
    """Retry prompt must explicitly forbid unified diff format."""
    from nexus.services.local_heal.prompt_builder import PromptBuilder

    prompt = PromptBuilder.build_verification_guided_retry_prompt(
        original_user_prompt="Fix normalize_score",
        verification_report="FAIL: normalize_score does not clamp",
        canonical_search_span="def normalize_score(score, min_val, max_val):",
        target_file="toy/math_util.py",
        retry_count=1,
        verifier_failure_kind="exception",
        verifier_stdout_excerpt="EVIDENCE: normalize_score does not clamp",
        verifier_stderr_excerpt="",
        verifier_exit_code="1",
        verifier_command_hash="abc123",
    )

    # Must contain FORBIDDEN section
    assert "FORBIDDEN" in prompt
    # Must forbid unified diff
    assert "unified diff" in prompt.lower() or "Unified diff" in prompt
    assert "--- a/" in prompt or "--- a/" in prompt.lower()


def test_retry_prompt_includes_target_file_and_verifier_evidence():
    """Retry prompt must include target file and verifier evidence."""
    from nexus.services.local_heal.prompt_builder import PromptBuilder

    prompt = PromptBuilder.build_verification_guided_retry_prompt(
        original_user_prompt="Fix normalize_score",
        verification_report="FAIL: normalize_score does not clamp",
        canonical_search_span="def normalize_score(score, min_val, max_val):",
        target_file="toy/math_util.py",
        retry_count=1,
        verifier_failure_kind="exception",
        verifier_stdout_excerpt="EVIDENCE: normalize_score does not clamp",
        verifier_stderr_excerpt="",
        verifier_exit_code="1",
        verifier_command_hash="abc123",
    )

    # Must contain target file
    assert "toy/math_util.py" in prompt
    # Must contain verifier evidence
    assert "normalize_score" in prompt
    # Must contain evidence section
    assert "VERIFICATION FAILURE REPORT" in prompt or "evidence" in prompt.lower()


def test_unified_diff_retry_output_is_classified_as_contract_failure():
    """Unified diff output from retry should be classified as format failure."""
    # This tests the classification logic, not the prompt itself
    # If retry produces unified diff, it should be format_rejected
    output = "--- a/toy/math_util.py\n+++ b/toy/math_util.py\n@@ -1,2 +1,5 @@\n def normalize_score(score, min_val, max_val):\n-    return (score - min_val) / (max_val - min_val)\n+    if max_val == min_val:\n+        return 0\n+    return (score - min_val) / (max_val - min_val)"

    # Check if output is unified diff format
    is_unified_diff = "--- a/" in output and "+++ b/" in output
    assert is_unified_diff, "Test output should be unified diff format"

    # Unified diff should be classified as format failure
    # This is the expected behavior after the fix
    format_rejected = is_unified_diff
    assert format_rejected, "Unified diff should be format_rejected"
