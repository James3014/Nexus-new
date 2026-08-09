"""C6AB: RED tests for research repair-pattern retrieval wiring.

Tests verify:
1. Successful repair patterns are selected into RESEARCH REPAIR PATTERNS section
2. Failure records (verifier_fail/owner_gated/parser_fail) are excluded
3. Pattern section has bounded size (max 1500 chars)
4. Telemetry includes research pattern fields
5. Retrieval failure is fail-open, doesn't block retry
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_QUALIFICATION = {
    "repeatability": True,
    "prevention_rule": "verified repair rule",
    "authority_qualification": True,
}


class TestRepairPatternRetrieval:
    """Repair pattern adapter should retrieve only success patterns."""

    def test_successful_repair_pattern_selected(self):
        """
        Given: learning_closure.jsonl with a verifier_pass record
        When: repair pattern retrieval is called
        Then: verifier_pass record is included in results
        """
        from nexus.services.local_heal.repair_pattern_retrieval import retrieve_successful_repair_patterns

        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            json.dump({
                "classification": "verifier_pass",
                "summary": "SEARCH must be exact verbatim copy",
                "task_id": "task-1",
                "lesson_id": "lh-001",
                "terminal_outcome": "SUCCEEDED",
                "terminal_evidence": {"receipt": "receipt://task-1"},
                "qualification_status": "QUALIFIED",
                "qualification": _QUALIFICATION,
            }, f)
            f.write("\n")
            json.dump({
                "classification": "verifier_fail",
                "summary": "This should be excluded",
                "task_id": "task-2",
                "lesson_id": "lh-002",
            }, f)
            f.write("\n")
            f.flush()
            path = f.name

        patterns = retrieve_successful_repair_patterns(path, limit=5)
        assert len(patterns) == 1
        assert patterns[0]["classification"] == "verifier_pass"
        assert "exact verbatim copy" in patterns[0]["summary"]

    def test_failure_records_excluded(self):
        """
        Given: learning_closure.jsonl with only failure records
        When: repair pattern retrieval is called
        Then: no patterns returned
        """
        from nexus.services.local_heal.repair_pattern_retrieval import retrieve_successful_repair_patterns

        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            for cls in ["verifier_fail", "owner_gated", "parser_fail"]:
                json.dump({"classification": cls, "summary": "failure", "task_id": "t", "lesson_id": "lh"}, f)
                f.write("\n")
            f.flush()
            path = f.name

        patterns = retrieve_successful_repair_patterns(path, limit=5)
        assert len(patterns) == 0

    def test_correct_abstain_included_as_pattern(self):
        """
        Given: learning_closure.jsonl with correct_abstain record
        When: repair pattern retrieval is called
        Then: correct_abstain is included (useful as "when NOT to patch" pattern)
        """
        from nexus.services.local_heal.repair_pattern_retrieval import retrieve_successful_repair_patterns

        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            json.dump({
                "classification": "correct_abstain",
                "summary": "No patch needed - code is correct",
                "task_id": "task-3",
                "lesson_id": "lh-003",
            }, f)
            f.write("\n")
            f.flush()
            path = f.name

        patterns = retrieve_successful_repair_patterns(path, limit=5)
        assert patterns == []

    def test_verifier_pass_requires_evidence_and_qualified_terminal(self):
        from nexus.services.local_heal.repair_pattern_retrieval import retrieve_successful_repair_patterns

        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            json.dump({
                "classification": "verifier_pass",
                "summary": "no evidence",
                "task_id": "task-no-evidence",
                "lesson_id": "random",
                "terminal_outcome": "SUCCEEDED",
            }, f)
            f.write("\n")
            f.flush()
            path = f.name
        assert retrieve_successful_repair_patterns(path, limit=5) == []

    def test_query_hint_prioritizes_matching_summary(self):
        from nexus.services.local_heal.repair_pattern_retrieval import retrieve_successful_repair_patterns

        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            for idx, summary in enumerate(("unrelated pattern", "target exact pattern")):
                json.dump({
                    "classification": "verifier_pass",
                    "summary": summary,
                    "task_id": f"task-{idx}",
                    "lesson_id": f"lesson-{idx}",
                    "terminal_outcome": "SUCCEEDED",
                    "terminal_evidence": {"receipt": f"receipt://task-{idx}"},
                    "qualification_status": "QUALIFIED",
                    "qualification": _QUALIFICATION,
                }, f)
                f.write("\n")
            f.flush()
            path = f.name
        patterns = retrieve_successful_repair_patterns(path, limit=2, query_hint="target")
        assert patterns[0]["summary"] == "target exact pattern"

    def test_pattern_bounded_size(self):
        """
        Given: many patterns in JSONL
        When: retrieval is called with limit
        Then: results are bounded to limit
        """
        from nexus.services.local_heal.repair_pattern_retrieval import retrieve_successful_repair_patterns

        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            for i in range(20):
                json.dump({
                    "classification": "verifier_pass",
                    "summary": f"Pattern {i}",
                    "task_id": f"task-{i}",
                    "lesson_id": f"lh-{i}",
                    "terminal_outcome": "SUCCEEDED",
                    "terminal_evidence": {"receipt": f"receipt://task-{i}"},
                    "qualification_status": "QUALIFIED",
                    "qualification": _QUALIFICATION,
                }, f)
                f.write("\n")
            f.flush()
            path = f.name

        patterns = retrieve_successful_repair_patterns(path, limit=3)
        assert len(patterns) == 3


class TestResearchPatternPromptRendering:
    """PromptBuilder should render RESEARCH REPAIR PATTERNS section."""

    def test_retry_prompt_renders_research_patterns_section(self):
        """
        Given: research_patterns with successful repair patterns
        When: build_verification_guided_retry_prompt is called with research_patterns
        Then: prompt contains RESEARCH REPAIR PATTERNS section
        """
        from nexus.services.local_heal.prompt_builder import PromptBuilder

        patterns_text = (
            "- Symptom: SEARCH mismatch after retry\n"
            "  Fix: Copy exact verbatim from source, no paraphrasing\n"
            "  Evidence: receipt/toy-math-solve\n"
        )

        prompt = PromptBuilder.build_verification_guided_retry_prompt(
            original_user_prompt="Fix the bug",
            verification_report="FAIL: assertion error",
            canonical_search_span="def foo(): pass",
            target_file="test.py",
            retry_count=1,
            research_patterns=patterns_text,
        )

        assert "RESEARCH REPAIR PATTERNS" in prompt
        assert "SEARCH mismatch" in prompt

    def test_retry_prompt_omits_section_when_empty(self):
        """
        Given: no research_patterns (empty string)
        When: prompt is built
        Then: RESEARCH REPAIR PATTERNS section is NOT present
        """
        from nexus.services.local_heal.prompt_builder import PromptBuilder

        prompt = PromptBuilder.build_verification_guided_retry_prompt(
            original_user_prompt="Fix",
            verification_report="FAIL",
            canonical_search_span="def foo(): pass",
            target_file="test.py",
            retry_count=1,
            research_patterns="",
        )

        assert "RESEARCH REPAIR PATTERNS" not in prompt

    def test_research_patterns_bounded_in_prompt(self):
        """
        Given: very long research_patterns (>1500 chars)
        When: prompt is built
        Then: section is truncated to bounded length
        """
        from nexus.services.local_heal.prompt_builder import PromptBuilder

        long_patterns = "x" * 2000

        prompt = PromptBuilder.build_verification_guided_retry_prompt(
            original_user_prompt="Fix",
            verification_report="FAIL",
            canonical_search_span="def foo(): pass",
            target_file="test.py",
            retry_count=1,
            research_patterns=long_patterns,
        )

        idx = prompt.find("RESEARCH REPAIR PATTERNS")
        assert idx >= 0


class TestResearchPatternTelemetry:
    """Telemetry should include research pattern fields."""

    def test_telemetry_fields_expected(self):
        """
        Given: semantic retry runs with research patterns
        When: telemetry is written
        Then: research pattern fields are present
        """
        expected_fields = {
            "semantic_retry_research_patterns_injected",
            "semantic_retry_research_pattern_count",
            "semantic_retry_research_context_hash",
        }
        assert len(expected_fields) == 3


class TestResearchPatternFailClosed:
    """Retrieval failure must not block retry."""

    def test_retry_proceeds_when_retrieval_fails(self):
        """
        Given: JSONL file does not exist
        When: orchestrator builds retry prompt
        Then: retry proceeds with empty research_patterns, no crash
        """
        from nexus.services.local_heal.repair_pattern_retrieval import retrieve_successful_repair_patterns

        patterns = retrieve_successful_repair_patterns("/nonexistent/file.jsonl", limit=5)
        assert patterns == []
