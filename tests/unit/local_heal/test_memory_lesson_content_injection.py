"""C6S: Memory lesson content injection tests.

Ensures retry prompt includes actual lesson summaries, not just IDs.
"""
from __future__ import annotations

import pytest


def test_provenance_bound_memory_context_includes_lineage_and_receipt_hash():
    from nexus.services.local_heal.memory_retrieval_adapter import (
        RetrievedLesson,
        _build_existing_retrieval_receipt,
        format_retrieved_lesson_context,
    )

    lesson = RetrievedLesson(
        finding_id="lep:lesson-1",
        summary="preserve the verified repair",
        relevance_score=1.0,
        provenance="receipt://lesson-1",
        source="canonical_episodic_memory",
        pattern_type="success",
        task_id="task-source",
        episode_id="lep:lesson-1",
        attempt_id="attempt-source",
        qualification_status="QUALIFIED",
        validity_state="active",
        evidence_ref="receipt://lesson-1",
    )

    receipt, receipt_hash, _lineage = _build_existing_retrieval_receipt(
        "preserve repair", [lesson]
    )
    context = format_retrieved_lesson_context([lesson], receipt, receipt_hash)

    assert "preserve the verified repair" in context
    assert "lesson_id=lep:lesson-1" in context
    assert "episode_id=lep:lesson-1" in context
    assert "source_task=task-source" in context
    assert "source_attempt=attempt-source" in context
    assert "qualification=QUALIFIED" in context
    assert "validity=active" in context
    assert "evidence=receipt://lesson-1" in context
    assert f"retrieval={receipt_hash}" in context


def test_provenance_bound_memory_context_fails_closed_on_tamper_or_stale_receipt():
    from dataclasses import replace

    from nexus.services.local_heal.memory_retrieval_adapter import (
        RetrievedLesson,
        _build_existing_retrieval_receipt,
        format_retrieved_lesson_context,
    )

    lesson = RetrievedLesson(
        finding_id="lep:lesson-2",
        summary="retain the verified invariant",
        relevance_score=1.0,
        provenance="receipt://lesson-2",
        source="canonical_episodic_memory",
        pattern_type="success",
        task_id="task-source",
        episode_id="lep:lesson-2",
        attempt_id="attempt-source",
        qualification_status="QUALIFIED",
        validity_state="active",
        evidence_ref="receipt://lesson-2",
    )
    receipt, receipt_hash, _lineage = _build_existing_retrieval_receipt("invariant", [lesson])
    assert format_retrieved_lesson_context([lesson], receipt, receipt_hash)

    tampered = dict(receipt)
    tampered["results"] = [dict(receipt["results"][0])]
    tampered["results"][0]["source_path"] = "receipt://substituted"
    assert format_retrieved_lesson_context([lesson], tampered, receipt_hash) == ""

    stale_hash = "sha256:" + "0" * 64
    assert format_retrieved_lesson_context([lesson], receipt, stale_hash) == ""

    substituted_lesson = replace(lesson, summary="substituted unbound content")
    assert format_retrieved_lesson_context([substituted_lesson], receipt, receipt_hash) == ""


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
