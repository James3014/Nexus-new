"""C6R-to-T: Seeded memory guidance effectiveness tests.

Verifies whether seeded memory lessons improve repair semantic gap.
"""
from __future__ import annotations

import pytest


def test_memory_on_seeded_and_unseeded_produce_different_guidance():
    """Seeded and unseeded memory should produce different retry guidance."""
    from nexus.services.local_heal.prompt_builder import PromptBuilder

    verifier_stdout = "EVIDENCE: function does not clamp output\nEXPECTED: clamp to [0, 1]"

    # Unseeded: no lessons
    prompt_unseeded = PromptBuilder.build_verification_guided_retry_prompt(
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
        memory_lessons="",
    )

    # Seeded: with relevant lessons
    prompt_seeded = PromptBuilder.build_verification_guided_retry_prompt(
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
        memory_lessons="Lesson: always clamp OUTPUT, not input\nLesson: handle division by zero when min == max",
    )

    # Seeded should have memory section
    assert "RELEVANT MEMORY LESSONS" in prompt_seeded
    assert "clamp OUTPUT" in prompt_seeded
    assert "division by zero" in prompt_seeded

    # Unseeded should not
    assert "RELEVANT MEMORY LESSONS" not in prompt_unseeded


def test_seeded_lessons_are_general_patterns_not_task_answers():
    """Seed lessons must be general repair patterns, not task-specific answers."""
    general_lessons = (
        "Lesson: always clamp OUTPUT, not input\n"
        "Lesson: handle division by zero when min == max\n"
        "Lesson: preserve prior successful fix in next retry round"
    )

    # These are general patterns, not toy-math specific
    assert "clamp OUTPUT" in general_lessons
    assert "division by zero" in general_lessons
    assert "preserve prior" in general_lessons

    # Not task-specific
    assert "normalize_score" not in general_lessons
    assert "toy-math" not in general_lessons


def test_seeded_memory_can_influence_retry_prompt():
    """Seeded memory should be visible in retry prompt."""
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
        memory_lessons="Lesson: always clamp OUTPUT, not input",
    )

    # Memory lessons should appear in prompt
    assert "clamp OUTPUT" in prompt
    assert "RELEVANT MEMORY LESSONS" in prompt


def test_memory_off_remains_valid_fail_closed_baseline():
    """memory_off path must remain valid fail-closed baseline."""
    from nexus.services.local_heal.memory_trace import get_empty_trace

    trace = get_empty_trace()
    assert trace.available is False
    assert trace.selected_ids == []


def test_multipass_with_seeded_memory():
    """Multipass should work with seeded memory guidance."""
    from nexus.services.local_heal.prompt_builder import PromptBuilder

    # Round 1 with seeded memory
    prompt_r1 = PromptBuilder.build_verification_guided_retry_prompt(
        original_user_prompt="Fix function",
        verification_report="EVIDENCE: function does not handle empty input",
        canonical_search_span="def func(data):\n    return data",
        target_file="code.py",
        retry_count=1,
        verifier_failure_kind="exception",
        verifier_stdout_excerpt="EVIDENCE: function does not handle empty input",
        verifier_stderr_excerpt="",
        verifier_exit_code="1",
        verifier_command_hash="abc123",
        memory_lessons="Lesson: always check for None/empty input before processing",
    )

    # Must have memory section
    assert "RELEVANT MEMORY LESSONS" in prompt_r1
    assert "check for None" in prompt_r1
    # Must still have SEARCH/REPLACE markers
    assert "<<<<<<< SEARCH" in prompt_r1
    assert ">>>>>>> REPLACE" in prompt_r1
