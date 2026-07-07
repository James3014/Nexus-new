"""Z4: RED tests for autoreason assertion prioritization in multipass semantic retry.

These tests verify that:
1. Autoreason can change the order of assertions processed in multipass
2. Autoreason cannot override verifier results
3. Fallback to deterministic ordering when autoreason is unavailable
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from pathlib import Path

import pytest


# --- Test 1: Autoreason priority changes multipass assertion order ---

class TestAutoreasonChangesAssertionOrder:
    """When autoreason is available, the multipass should process assertions
    in autoreason-ranked order, NOT the default first-EVIDENCE-line order."""

    def test_autoreason_priority_changes_multipass_assertion_order(self):
        """
        Given: verifier stdout has 3 EVIDENCE assertions of different types
        When: prioritization runs
        Then: timeout assertions come first, then assertion-type, then exception-type
        """
        from nexus.services.local_heal.orchestrator import HealOrchestrator

        orchestrator = HealOrchestrator.__new__(HealOrchestrator)
        orchestrator.governance_gate = MagicMock()
        orchestrator.receipt_writer = None

        mock_ctx = MagicMock()
        mock_ctx.op.verifier_stdout_excerpt = "EVIDENCE: tests failed"
        mock_ctx.op.final_patch = "some patch"
        mock_ctx.op.attempt = 1
        mock_ctx.op.failure_reason = "VERIFIER_FAIL"

        assertions = [
            "EVIDENCE: assert result[0].name == 'x'",         # assertion type (short)
            "EVIDENCE: timeout exceeded after 30s",            # timeout type (highest priority)
            "EVIDENCE: ValueError: invalid input",             # exception type
        ]

        ordered = orchestrator._prioritize_assertions_with_autoreason(assertions, mock_ctx)

        # Timeout should come first (highest fixability priority)
        assert "timeout" in ordered[0].lower(), (
            f"Expected timeout assertion first, got: {ordered[0]}"
        )
        # Assertion type should come second
        assert "assert" in ordered[1].lower(), (
            f"Expected assertion-type second, got: {ordered[1]}"
        )
        # Exception type should come last
        assert "error" in ordered[2].lower() or "exception" in ordered[2].lower(), (
            f"Expected exception-type last, got: {ordered[2]}"
        )

    def test_autoreason_cannot_override_verifier(self):
        """
        Given: autoreason produces ranking
        Then: the ranking is advisory only — it cannot change verifier verdict
        """
        from nexus.services.local_heal.reasoning_advisory_bridge import apply_autoreason_advisory

        mock_ctx = MagicMock()
        mock_ctx.op.final_patch = "patch"
        mock_ctx.op.problem_statement = "test"
        mock_ctx.op.evidence_refs = ["ref1"]
        mock_ctx.op.instance_id = "task-1"

        advisory = apply_autoreason_advisory(mock_ctx)

        assert advisory["no_override"] is True
        assert advisory["cannot_override_verifier"] is True
        assert advisory["cannot_bypass_owner_gate"] is True

    def test_autoreason_fallback_when_unavailable(self):
        """
        Given: autoreason is not available
        When: multipass processes assertions
        Then: fallback to deterministic heuristic ordering
        """
        from nexus.services.local_heal.orchestrator import HealOrchestrator

        orchestrator = HealOrchestrator.__new__(HealOrchestrator)

        mock_ctx = MagicMock()
        mock_ctx.op.verifier_stdout_excerpt = (
            "EVIDENCE: assert first\n"
            "EVIDENCE: assert second\n"
        )

        assertions = [
            "EVIDENCE: assert first",
            "EVIDENCE: assert second",
        ]

        ordered = orchestrator._prioritize_assertions_with_autoreason(assertions, mock_ctx)

        # Both are same type; deterministic ordering should be stable
        assert len(ordered) == 2
        assert set(ordered) == set(assertions)


# --- Test 2: Memory lesson structure ---

class TestMemoryLessonStructuring:
    """Memory lessons in retry prompts should be structured with
    classification priority, not injected as flat text blobs."""

    def test_memory_lesson_structured_not_flat_blob(self):
        """
        Given: memory lessons with different classifications (success/failure)
        When: lessons are injected into retry prompt
        Then: they should be structured with classification labels and prioritized
        """
        from nexus.services.local_heal.prompt_builder import PromptBuilder

        lessons_text = (
            "Lesson [success] (id: lh-001):\n"
            "  - SEARCH must be exact verbatim copy\n"
            "Lesson [failure] (id: lh-002):\n"
            "  - Do not add markdown fences around SEARCH/REPLACE\n"
        )

        prompt = PromptBuilder.build_verification_guided_retry_prompt(
            original_user_prompt="Fix the bug",
            verification_report="FAIL: assertion error",
            canonical_search_span="def foo(): pass",
            target_file="test.py",
            retry_count=1,
            memory_lessons=lessons_text,
        )

        # Verify structured format is present
        assert "RELEVANT MEMORY LESSONS" in prompt
        assert "Lesson [success]" in prompt
        assert "Lesson [failure]" in prompt

    def test_failure_record_not_treated_as_success_pattern(self):
        """
        Given: a memory lesson classified as 'failure'
        When: it appears in retry prompt guidance
        Then: it must be labeled as failure (not success)
        """
        from nexus.services.local_heal.learning_closure_bridge import classify_learning_outcome

        mock_ctx = MagicMock()
        mock_ctx.op.solve_eligible = False
        mock_ctx.op.failure_reason = "VERIFIER_FAIL: assertion error"
        mock_ctx.op.final_patch = "some patch"

        classification = classify_learning_outcome(mock_ctx)
        assert classification == "verifier_fail"
        assert classification != "verifier_pass"

    def test_next_retry_can_consume_previous_round_lesson(self):
        """
        Given: round 1 failed with SEARCH_MISMATCH
        When: round 2 retry prompt is built
        Then: the failure_feedback includes SEARCH_MISMATCH-specific guidance
        """
        from nexus.services.local_heal.prompt_builder import PromptBuilder

        prompt = PromptBuilder.build_patch_user_prompt(
            problem_statement="Fix bug",
            repro_evidence="test fails",
            plan=MagicMock(search_symbols=["func"], repair_strategy="surgical fix"),
            localized_files=[],
            failure_reason="SEARCH_MISMATCH: search block did not match source",
            attempt=2,
        )

        assert "SEARCH_MISMATCH" in prompt
        assert "EXACT verbatim copy" in prompt
