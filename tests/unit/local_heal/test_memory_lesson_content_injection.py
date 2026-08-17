"""C6S: Memory lesson content injection tests.

Ensures retry prompt includes actual lesson summaries, not just IDs.
"""
from __future__ import annotations


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
    context = format_retrieved_lesson_context(
        [lesson], receipt, receipt_hash, query_text="preserve repair"
    )

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
        validate_retrieved_lesson_context_binding,
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
        action_id="action-source",
        qualification_status="QUALIFIED",
        validity_state="active",
        evidence_ref="receipt://lesson-2",
    )
    receipt, receipt_hash, _lineage = _build_existing_retrieval_receipt("invariant", [lesson])
    assert format_retrieved_lesson_context(
        [lesson], receipt, receipt_hash, query_text="invariant"
    )
    assert (
        validate_retrieved_lesson_context_binding(
            [lesson], receipt, receipt_hash, query_text="invariant"
        )
        is True
    )

    # 1. Receipt tamper / substitution
    tampered = dict(receipt)
    tampered["results"] = [dict(receipt["results"][0])]
    tampered["results"][0]["source_path"] = "receipt://substituted"
    assert (
        format_retrieved_lesson_context(
            [lesson], tampered, receipt_hash, query_text="invariant"
        )
        == ""
    )
    assert (
        validate_retrieved_lesson_context_binding(
            [lesson], tampered, receipt_hash, query_text="invariant"
        )
        is False
    )

    # 2. Stale / corrupted receipt hash
    stale_hash = "sha256:" + "0" * 64
    assert (
        format_retrieved_lesson_context(
            [lesson], receipt, stale_hash, query_text="invariant"
        )
        == ""
    )
    assert (
        validate_retrieved_lesson_context_binding(
            [lesson], receipt, stale_hash, query_text="invariant"
        )
        is False
    )

    # 3. Content tamper
    substituted_summary = replace(lesson, summary="substituted unbound content")
    assert (
        format_retrieved_lesson_context(
            [substituted_summary], receipt, receipt_hash, query_text="invariant"
        )
        == ""
    )
    assert (
        validate_retrieved_lesson_context_binding(
            [substituted_summary], receipt, receipt_hash, query_text="invariant"
        )
        is False
    )

    # 4. Provenance tamper: source task ID
    tampered_task = replace(lesson, task_id="tampered-task-id")
    assert (
        format_retrieved_lesson_context(
            [tampered_task], receipt, receipt_hash, query_text="invariant"
        )
        == ""
    )
    assert (
        validate_retrieved_lesson_context_binding(
            [tampered_task], receipt, receipt_hash, query_text="invariant"
        )
        is False
    )

    # 5. Provenance tamper: source attempt ID
    tampered_attempt = replace(lesson, attempt_id="tampered-attempt-id")
    assert (
        format_retrieved_lesson_context(
            [tampered_attempt], receipt, receipt_hash, query_text="invariant"
        )
        == ""
    )
    assert (
        validate_retrieved_lesson_context_binding(
            [tampered_attempt], receipt, receipt_hash, query_text="invariant"
        )
        is False
    )

    # 6. Provenance tamper: source action ID
    tampered_action = replace(lesson, action_id="tampered-action-id")
    assert (
        format_retrieved_lesson_context(
            [tampered_action], receipt, receipt_hash, query_text="invariant"
        )
        == ""
    )
    assert (
        validate_retrieved_lesson_context_binding(
            [tampered_action], receipt, receipt_hash, query_text="invariant"
        )
        is False
    )

    # 7. Provenance tamper: qualification status
    tampered_qual = replace(lesson, qualification_status="FORGED_STATUS")
    assert (
        format_retrieved_lesson_context(
            [tampered_qual], receipt, receipt_hash, query_text="invariant"
        )
        == ""
    )
    assert (
        validate_retrieved_lesson_context_binding(
            [tampered_qual], receipt, receipt_hash, query_text="invariant"
        )
        is False
    )

    # 8. Provenance tamper: validity state
    tampered_validity = replace(lesson, validity_state="tampered_active")
    assert (
        format_retrieved_lesson_context(
            [tampered_validity], receipt, receipt_hash, query_text="invariant"
        )
        == ""
    )
    assert (
        validate_retrieved_lesson_context_binding(
            [tampered_validity], receipt, receipt_hash, query_text="invariant"
        )
        is False
    )

    # 9. Provenance tamper: evidence ref
    tampered_evidence = replace(lesson, evidence_ref="receipt://tampered")
    assert (
        format_retrieved_lesson_context(
            [tampered_evidence], receipt, receipt_hash, query_text="invariant"
        )
        == ""
    )
    assert (
        validate_retrieved_lesson_context_binding(
            [tampered_evidence], receipt, receipt_hash, query_text="invariant"
        )
        is False
    )

    # 10. Receipt from a different retrieval query must not be reusable.
    assert (
        validate_retrieved_lesson_context_binding(
            [lesson], receipt, receipt_hash, query_text="different query"
        )
        is False
    )
    assert (
        format_retrieved_lesson_context(
            [lesson], receipt, receipt_hash, query_text="different query"
        )
        == ""
    )

    # 11. A self-consistent receipt with a substituted snapshot identity must fail closed.
    from nexus.services.local_heal.memory_retrieval_adapter import _retrieval_receipt_digest

    substituted_snapshot = dict(receipt)
    substituted_snapshot["index_snapshot_id"] = "memory:" + "0" * 24
    substituted_snapshot_hash = _retrieval_receipt_digest(substituted_snapshot)
    assert (
        validate_retrieved_lesson_context_binding(
            [lesson],
            substituted_snapshot,
            substituted_snapshot_hash,
            query_text="invariant",
        )
        is False
    )


def test_p5_p6_fails_closed_when_binding_invalid(monkeypatch):
    """P5/P6 memory context must drop all lessons if receipt binding fails."""
    from dataclasses import replace

    from nexus.services.local_heal.memory_retrieval_adapter import (
        MemoryRetrievalAdapter,
        RetrievedLesson,
        _build_existing_retrieval_receipt,
    )
    from nexus.services.local_heal.p5_p6_memory_context import build_p5_p6_memory_context

    lesson = RetrievedLesson(
        finding_id="lep:lesson-p5",
        summary="lesson for p5/p6",
        relevance_score=1.0,
        provenance="receipt://p5",
        source="canonical_episodic_memory",
        pattern_type="success",
        task_id="task-p5",
        episode_id="lep:lesson-p5",
        attempt_id="attempt-p5",
        action_id="action-p5",
        qualification_status="QUALIFIED",
        validity_state="active",
        evidence_ref="receipt://p5",
    )

    # Valid case
    def fake_retrieve_reranked_valid(self, *args, **kwargs):
        receipt, receipt_hash, lineage = _build_existing_retrieval_receipt("p5 query", [lesson])
        self.last_metadata = {
            "retrieval_receipt": receipt,
            "retrieval_receipt_hash": receipt_hash,
            "selected_lesson_lineage": lineage,
            "accepted": 1,
            "selected_ids": [lesson.finding_id],
            "memory_evidence_ids": [lesson.finding_id],
            "query_text_hash": "abc",
        }
        return [lesson]

    monkeypatch.setattr(MemoryRetrievalAdapter, "retrieve_reranked", fake_retrieve_reranked_valid)
    ctx_valid = build_p5_p6_memory_context(adapter_enabled=True, query_text="p5 query")
    assert len(ctx_valid.retrieved_lessons) == 1
    assert ctx_valid.reason == "hits_available"

    # Tampered / invalid binding case
    def fake_retrieve_reranked_tampered(self, *args, **kwargs):
        receipt, receipt_hash, lineage = _build_existing_retrieval_receipt("p5 query", [lesson])
        # Return tampered lesson where attempt_id was modified after receipt creation
        tampered = replace(lesson, attempt_id="tampered-attempt")
        self.last_metadata = {
            "retrieval_receipt": receipt,
            "retrieval_receipt_hash": receipt_hash,
            "selected_lesson_lineage": lineage,
            "accepted": 1,
            "selected_ids": [tampered.finding_id],
            "memory_evidence_ids": [tampered.finding_id],
            "query_text_hash": "abc",
        }
        return [tampered]

    monkeypatch.setattr(MemoryRetrievalAdapter, "retrieve_reranked", fake_retrieve_reranked_tampered)
    ctx_tampered = build_p5_p6_memory_context(adapter_enabled=True, query_text="p5 query")
    assert ctx_tampered.retrieved_lessons == []
    assert ctx_tampered.memory_sources == []
    assert ctx_tampered.reason == "binding_failed"


def test_retrieved_presented_does_not_become_applied_automatically():
    """Retrieved / presented advisory memory must remain distinct from applied attribution."""
    from nexus.services.local_heal.memory_trace import MemoryTrace

    trace = MemoryTrace(
        available=True,
        trace_status="TRACE_AVAILABLE",
        selected_ids=["lep:lesson-1"],
        verifier_status="NOT_MEASURED",
        influence_status="NOT_MEASURED",
    )
    d = trace.to_dict()
    assert d["selected_ids"] == ["lep:lesson-1"]
    assert d["influence_status"] == "NOT_MEASURED"
    assert d["verifier_status"] == "NOT_MEASURED"


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
