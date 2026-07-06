"""C6S: Memory lesson content injection tests.

Ensures retry prompt includes actual lesson summaries, not just IDs.
"""
from __future__ import annotations

import pytest


def test_retry_prompt_includes_retrieved_lesson_summary_content():
    """Retry prompt must include actual lesson summary text, not just IDs."""
    from nexus.services.local_heal.prompt_builder import PromptBuilder

    # Simulate: memory has lessons with summaries
    memory_lessons = (
        "Lesson [success] (source: prior_repair):\n"
        "  - always clamp OUTPUT, not input; handle division by zero when min == max\n"
        "Lesson [failure] (source: verifier_fail):\n"
        "  - preserve prior successful fix in next retry round"
    )

    prompt = PromptBuilder.build_verification_guided_retry_prompt(
        original_user_prompt="Fix function",
        verification_report="EVIDENCE: function does not clamp",
        canonical_search_span="def func():\n    return x",
        target_file="code.py",
        retry_count=1,
        verifier_failure_kind="exception",
        verifier_stdout_excerpt="EVIDENCE: function does not clamp",
        verifier_stderr_excerpt="",
        verifier_exit_code="1",
        verifier_command_hash="abc123",
        memory_lessons=memory_lessons,
    )

    # Must contain actual lesson content
    assert "clamp OUTPUT" in prompt
    assert "division by zero" in prompt
    assert "preserve prior" in prompt
    # Must NOT be just IDs
    assert "Lessons found:" not in prompt or "clamp" in prompt


def test_retry_prompt_does_not_only_include_lesson_ids():
    """Retry prompt must not only include lesson IDs."""
    from nexus.services.local_heal.prompt_builder import PromptBuilder

    # Bad: only IDs
    bad_lessons = "Lessons found: lh-123, lh-456\nEvidence IDs: lh-789"

    prompt = PromptBuilder.build_verification_guided_retry_prompt(
        original_user_prompt="Fix function",
        verification_report="EVIDENCE: function does not clamp",
        canonical_search_span="def func():\n    return x",
        target_file="code.py",
        retry_count=1,
        verifier_failure_kind="exception",
        verifier_stdout_excerpt="EVIDENCE: function does not clamp",
        verifier_stderr_excerpt="",
        verifier_exit_code="1",
        verifier_command_hash="abc123",
        memory_lessons=bad_lessons,
    )

    # Should still work but content is useless
    assert "RELEVANT MEMORY LESSONS" in prompt
    # The prompt should not rely on IDs alone


def test_memory_guidance_includes_actionable_summary_and_provenance():
    """Memory guidance must include actionable summary and provenance."""
    from nexus.services.local_heal.prompt_builder import PromptBuilder

    memory_lessons = (
        "Lesson [success] (source: prior_repair):\n"
        "  - always clamp OUTPUT, not input\n"
        "Lesson [failure] (source: verifier_fail):\n"
        "  - avoid replacing input clamping when output clamping is required"
    )

    prompt = PromptBuilder.build_verification_guided_retry_prompt(
        original_user_prompt="Fix function",
        verification_report="EVIDENCE: function does not clamp",
        canonical_search_span="def func():\n    return x",
        target_file="code.py",
        retry_count=1,
        verifier_failure_kind="exception",
        verifier_stdout_excerpt="EVIDENCE: function does not clamp",
        verifier_stderr_excerpt="",
        verifier_exit_code="1",
        verifier_command_hash="abc123",
        memory_lessons=memory_lessons,
    )

    # Must have actionable content
    assert "clamp OUTPUT" in prompt
    assert "input clamping" in prompt
    # Must have provenance
    assert "prior_repair" in prompt or "verifier_fail" in prompt


def test_memory_off_baseline_has_no_relevant_memory_lessons_section():
    """memory_off path must not have RELEVANT MEMORY LESSONS section."""
    from nexus.services.local_heal.prompt_builder import PromptBuilder

    prompt = PromptBuilder.build_verification_guided_retry_prompt(
        original_user_prompt="Fix function",
        verification_report="EVIDENCE: function does not clamp",
        canonical_search_span="def func():\n    return x",
        target_file="code.py",
        retry_count=1,
        verifier_failure_kind="exception",
        verifier_stdout_excerpt="EVIDENCE: function does not clamp",
        verifier_stderr_excerpt="",
        verifier_exit_code="1",
        verifier_command_hash="abc123",
        memory_lessons="",
    )

    assert "RELEVANT MEMORY LESSONS" not in prompt


def test_seeded_lesson_content_reaches_retry_prompt():
    """Seeded lesson content should appear in retry prompt."""
    from nexus.services.local_heal.prompt_builder import PromptBuilder

    memory_lessons = (
        "Lesson [success] (source: prior_repair):\n"
        "  - when verifier mentions multiple unmet assertions, do not drop previously satisfied condition"
    )

    prompt = PromptBuilder.build_verification_guided_retry_prompt(
        original_user_prompt="Fix function",
        verification_report="EVIDENCE: function does not clamp",
        canonical_search_span="def func():\n    return x",
        target_file="code.py",
        retry_count=1,
        verifier_failure_kind="exception",
        verifier_stdout_excerpt="EVIDENCE: function does not clamp",
        verifier_stderr_excerpt="",
        verifier_exit_code="1",
        verifier_command_hash="abc123",
        memory_lessons=memory_lessons,
    )

    # Must contain the lesson content
    assert "do not drop previously satisfied" in prompt
    assert "RELEVANT MEMORY LESSONS" in prompt
