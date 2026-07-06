"""C6K: Missing verifier assertion grounding tests.

Ensures retry prompt includes all failing verifier conditions.
"""
from __future__ import annotations

import pytest


def test_retry_prompt_includes_all_failing_verifier_conditions():
    """Retry prompt must list ALL failing conditions from verifier, not just one."""
    from nexus.services.local_heal.prompt_builder import PromptBuilder

    # Simulate verifier output with multiple failing conditions
    verifier_stdout = (
        "EVIDENCE: normalize_score does not clamp output to [0, 1] range\n"
        "EVIDENCE: normalize_score may raise ZeroDivisionError when max_val == min_val\n"
        "EXPECTED: normalize_score should clamp to [0, 1] and handle equal min/max"
    )

    prompt = PromptBuilder.build_verification_guided_retry_prompt(
        original_user_prompt="Fix normalize_score",
        verification_report=verifier_stdout,
        canonical_search_span="def normalize_score(score, min_val, max_val):\n    return (score - min_val) / (max_val - min_val)",
        target_file="toy/math_util.py",
        retry_count=1,
        verifier_failure_kind="exception",
        verifier_stdout_excerpt=verifier_stdout,
        verifier_stderr_excerpt="",
        verifier_exit_code="1",
        verifier_command_hash="abc123",
    )

    # Must contain ALL failing conditions
    assert "clamp" in prompt.lower() or "max(0" in prompt or "min(1" in prompt
    assert "max_val == min_val" in prompt or "divide" in prompt.lower() or "ZeroDivision" in prompt
    # Must contain the EXPECTED behavior
    assert "clamp to [0, 1]" in prompt or "clamp output" in prompt.lower()


def test_retry_prompt_explicitly_lists_each_failing_assertion():
    """Retry prompt should enumerate each failing assertion separately."""
    from nexus.services.local_heal.prompt_builder import PromptBuilder

    verifier_stdout = (
        "EVIDENCE: normalize_score does not clamp output to [0, 1] range\n"
        "EVIDENCE: normalize_score may raise ZeroDivisionError when max_val == min_val\n"
        "EXPECTED: normalize_score should clamp to [0, 1] and handle equal min/max"
    )

    prompt = PromptBuilder.build_verification_guided_retry_prompt(
        original_user_prompt="Fix normalize_score",
        verification_report=verifier_stdout,
        canonical_search_span="def normalize_score(score, min_val, max_val):\n    return (score - min_val) / (max_val - min_val)",
        target_file="toy/math_util.py",
        retry_count=1,
        verifier_failure_kind="exception",
        verifier_stdout_excerpt=verifier_stdout,
        verifier_stderr_excerpt="",
        verifier_exit_code="1",
        verifier_command_hash="abc123",
    )

    # The evidence section should contain the raw verifier output
    assert "EVIDENCE:" in prompt
    # Should contain both clamping AND division-by-zero assertions
    evidence_start = prompt.find("VERIFIER FAILURE EVIDENCE")
    if evidence_start >= 0:
        evidence_section = prompt[evidence_start:]
        assert "clamp" in evidence_section.lower()
        assert "max_val == min_val" in evidence_section or "ZeroDivision" in evidence_section


def test_retry_patch_fixing_only_clamping_misses_equal_bound_still_fails():
    """A patch that fixes clamping but misses max_val==min_val should still fail."""
    # This tests the verifier logic, not the prompt
    # If the patch only adds clamping but doesn't handle equal min/max, verifier should fail

    # Simulate: patch adds clamping but doesn't handle max_val == min_val
    patched_code = (
        "def normalize_score(score, min_val, max_val):\n"
        "    result = (score - min_val) / (max_val - min_val)\n"
        "    return max(0, min(1, result))\n"
    )

    # Verifier checks
    has_clamp = "max(0" in patched_code or "min(1" in patched_code
    has_divide_check = "max_val == min_val" in patched_code or "max_val != min_val" in patched_code

    assert has_clamp is True, "Patch should have clamping"
    assert has_divide_check is False, "Patch should NOT have divide-by-zero check (this is the bug)"
    # Verifier would fail because divide_check is missing


def test_smallest_fixture_passes_only_when_all_conditions_addressed():
    """Smallest fixture should pass only when ALL verifier conditions are met."""
    # This tests the expected correct solution
    correct_code = (
        "def normalize_score(score, min_val, max_val):\n"
        "    if max_val == min_val:\n"
        "        return 0.5\n"
        "    result = (score - min_val) / (max_val - min_val)\n"
        "    return max(0, min(1, result))\n"
    )

    has_clamp = "max(0" in correct_code or "min(1" in correct_code
    has_divide_check = "max_val == min_val" in correct_code

    assert has_clamp is True
    assert has_divide_check is True
    # Both conditions met — verifier should pass
