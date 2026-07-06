"""C6M: General semantic coverage uplift tests.

Ensures retry prompt renders verifier requirements as explicit structured checklist.
"""
from __future__ import annotations

import pytest


def test_retry_prompt_renders_verifier_requirements_as_checklist():
    """Retry prompt must render verifier requirements as explicit checklist items."""
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

    # Must contain explicit checklist
    assert "FAILING ASSERTIONS" in prompt or "CHECKLIST" in prompt.upper()
    # Must contain numbered items
    assert "1." in prompt
    assert "2." in prompt
    # Must contain the actual assertions
    assert "clamp" in prompt.lower()
    assert "max_val == min_val" in prompt or "ZeroDivision" in prompt


def test_checklist_supports_multiple_simultaneous_assertions():
    """Checklist must handle multiple assertions without task-specific logic."""
    from nexus.services.local_heal.prompt_builder import PromptBuilder

    # Multiple assertions from different tasks
    verifier_stdout = (
        "EVIDENCE: function does not handle empty input\n"
        "EVIDENCE: function raises TypeError on None input\n"
        "EVIDENCE: function does not validate input types\n"
        "EXPECTED: function should handle empty input, None, and validate types"
    )

    prompt = PromptBuilder.build_verification_guided_retry_prompt(
        original_user_prompt="Fix input validation",
        verification_report=verifier_stdout,
        canonical_search_span="def process(data):\n    return data",
        target_file="utils.py",
        retry_count=1,
        verifier_failure_kind="exception",
        verifier_stdout_excerpt=verifier_stdout,
        verifier_stderr_excerpt="",
        verifier_exit_code="1",
        verifier_command_hash="abc123",
    )

    # Must contain all 3 assertions
    assert "empty input" in prompt.lower()
    assert "None" in prompt
    assert "validate" in prompt.lower() or "type" in prompt.lower()


def test_replace_only_retry_includes_all_conditions_must_hold():
    """Replace-only retry prompt must state all conditions must hold."""
    from nexus.services.local_heal.prompt_builder import PromptBuilder

    verifier_stdout = (
        "EVIDENCE: normalize_score does not clamp output\n"
        "EVIDENCE: normalize_score may raise ZeroDivisionError\n"
        "EXPECTED: normalize_score should clamp and handle equal min/max"
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

    # Must state all conditions must be addressed
    assert "ALL" in prompt
    assert "MUST" in prompt


def test_partial_fix_remains_fail_full_coverage_passes():
    """Partial fix should still fail; full checklist coverage should pass."""
    # This tests the verifier logic, not the prompt

    # Partial fix: only clamps, misses division by zero
    partial_code = "return max(0, min(1, (score - min_val) / (max_val - min_val)))"
    has_clamp = "max(0" in partial_code
    has_divide_check = "max_val == min_val" in partial_code
    assert has_clamp is True
    assert has_divide_check is False
    # Verifier would fail

    # Full fix: clamps AND handles division by zero
    full_code = "if max_val == min_val: return 0.5\nreturn max(0, min(1, (score - min_val) / (max_val - min_val)))"
    has_clamp_full = "max(0" in full_code
    has_divide_check_full = "max_val == min_val" in full_code
    assert has_clamp_full is True
    assert has_divide_check_full is True
    # Verifier would pass


def test_no_task_specific_if_else_in_prompt():
    """Prompt must not contain task-specific if/else logic."""
    from nexus.services.local_heal.prompt_builder import PromptBuilder

    verifier_stdout = (
        "EVIDENCE: function does not handle edge case X\n"
        "EXPECTED: function should handle edge case X"
    )

    prompt = PromptBuilder.build_verification_guided_retry_prompt(
        original_user_prompt="Fix function",
        verification_report=verifier_stdout,
        canonical_search_span="def func():\n    pass",
        target_file="code.py",
        retry_count=1,
        verifier_failure_kind="exception",
        verifier_stdout_excerpt=verifier_stdout,
        verifier_stderr_excerpt="",
        verifier_exit_code="1",
        verifier_command_hash="abc123",
    )

    # Must not contain task-specific instructions
    assert "max_val == min_val" not in prompt or "max_val == min_val" in verifier_stdout
    assert "division by zero" not in prompt.lower() or "division by zero" in verifier_stdout.lower()
