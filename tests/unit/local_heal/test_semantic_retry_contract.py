"""C6I: Semantic retry contract tests.

Ensures retry prompt enforces semantic correctness, not just format.
"""
from __future__ import annotations

import pytest


def test_retry_prompt_contains_failing_behavior_requirement():
    """Retry prompt must include the specific failing behavior from verifier."""
    from nexus.services.local_heal.prompt_builder import PromptBuilder

    prompt = PromptBuilder.build_verification_guided_retry_prompt(
        original_user_prompt="Fix normalize_score",
        verification_report="EVIDENCE: normalize_score does not clamp output to [0, 1] range\nEVIDENCE: normalize_score does not handle max_val == min_val case\nEXPECTED: normalize_score should clamp to [0, 1] and handle equal min/max",
        canonical_search_span="def normalize_score(score, min_val, max_val):\n    return (score - min_val) / (max_val - min_val)",
        target_file="toy/math_util.py",
        retry_count=1,
        verifier_failure_kind="exception",
        verifier_stdout_excerpt="EVIDENCE: normalize_score does not clamp output to [0, 1] range\nEVIDENCE: normalize_score does not handle max_val == min_val case\nEXPECTED: normalize_score should clamp to [0, 1] and handle equal min/max",
        verifier_stderr_excerpt="",
        verifier_exit_code="1",
        verifier_command_hash="abc123",
    )

    # Must contain the failing behavior requirement
    assert "clamp" in prompt.lower() or "max(0" in prompt or "min(1" in prompt
    assert "max_val == min_val" in prompt or "divide" in prompt.lower()


def test_retry_prompt_contains_expected_post_edit_condition():
    """Retry prompt must specify what the code should do after the fix."""
    from nexus.services.local_heal.prompt_builder import PromptBuilder

    prompt = PromptBuilder.build_verification_guided_retry_prompt(
        original_user_prompt="Fix normalize_score",
        verification_report="EVIDENCE: normalize_score does not clamp output to [0, 1] range\nEXPECTED: normalize_score should clamp to [0, 1] and handle equal min/max",
        canonical_search_span="def normalize_score(score, min_val, max_val):\n    return (score - min_val) / (max_val - min_val)",
        target_file="toy/math_util.py",
        retry_count=1,
        verifier_failure_kind="exception",
        verifier_stdout_excerpt="EVIDENCE: normalize_score does not clamp output to [0, 1] range\nEXPECTED: normalize_score should clamp to [0, 1] and handle equal min/max",
        verifier_stderr_excerpt="",
        verifier_exit_code="1",
        verifier_command_hash="abc123",
    )

    # Must contain expected behavior
    assert "clamp" in prompt.lower() or "[0, 1]" in prompt or "expected" in prompt.lower()


def test_retry_prompt_forbids_noop_or_equivalent_patch():
    """Retry prompt must forbid no-op or equivalent patches."""
    from nexus.services.local_heal.prompt_builder import PromptBuilder

    prompt = PromptBuilder.build_verification_guided_retry_prompt(
        original_user_prompt="Fix normalize_score",
        verification_report="FAIL: normalize_score does not clamp",
        canonical_search_span="def normalize_score(score, min_val, max_val):\n    return (score - min_val) / (max_val - min_val)",
        target_file="toy/math_util.py",
        retry_count=1,
        verifier_failure_kind="exception",
        verifier_stdout_excerpt="EVIDENCE: normalize_score does not clamp",
        verifier_stderr_excerpt="",
        verifier_exit_code="1",
        verifier_command_hash="abc123",
    )

    # Must contain FORBIDDEN section (already added in C6H)
    assert "FORBIDDEN" in prompt


def test_retry_prompt_requires_edit_to_targeted_symbol_or_file():
    """Retry prompt must require edit to the specific target file/symbol."""
    from nexus.services.local_heal.prompt_builder import PromptBuilder

    prompt = PromptBuilder.build_verification_guided_retry_prompt(
        original_user_prompt="Fix normalize_score",
        verification_report="FAIL: normalize_score does not clamp",
        canonical_search_span="def normalize_score(score, min_val, max_val):\n    return (score - min_val) / (max_val - min_val)",
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
    # Must contain SEARCH/REPLACE markers
    assert "<<<<<<< SEARCH" in prompt
    assert ">>>>>>> REPLACE" in prompt
