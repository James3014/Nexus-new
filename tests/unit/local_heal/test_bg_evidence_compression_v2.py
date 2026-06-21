"""BG: Unit tests for Evidence Context Compression v2 and Memory Reranking."""
from __future__ import annotations

import pytest
from nexus.services.local_heal.evidence_compactor import EvidenceCompactor
from nexus.services.local_heal.memory_retrieval_adapter import MemoryRetrievalAdapter, RetrievedLesson


# ---------------------------------------------------------------------------
# EvidenceCompactor.compact_v2
# ---------------------------------------------------------------------------

class TestCompactV2:
    def _make_long_evidence(self, extra: str = "") -> str:
        """Generate evidence > 3000 chars."""
        tb = "Traceback (most recent call last):\n"
        for i in range(40):
            tb += f'  File "/opt/homebrew/lib/python/site-packages/lib{i}.py", line {i}, in func{i}\n'
            tb += f"    some_call_{i}()\n"
        tb += 'FAILED tests/test_foo.py::test_bar - AssertionError: expected True got False'
        tb += "\n" + extra
        return tb

    def test_compact_v2_fits_within_limit(self):
        evidence = self._make_long_evidence()
        result = EvidenceCompactor.compact_v2(evidence, limit=1000)
        assert len(result) <= 1000

    def test_compact_v2_short_evidence_unchanged(self):
        short = "AssertionError: failed\nsome line"
        result = EvidenceCompactor.compact_v2(short, limit=3000)
        assert result == short

    def test_compact_v2_empty_evidence_unchanged(self):
        assert EvidenceCompactor.compact_v2("") == ""
        assert EvidenceCompactor.compact_v2(None) is None

    def test_compact_v2_anchor_symbol_boosted(self):
        evidence = "\n".join([
            "irrelevant line " * 50,
            "FAILED test: my_anchor_func raised AssertionError",
            "another unrelated line " * 50,
        ])
        # Force limit so selection is forced
        result = EvidenceCompactor.compact_v2(
            evidence, anchor_symbol="my_anchor_func", limit=120
        )
        assert "my_anchor_func" in result

    def test_compact_v2_deduplication(self):
        # Same content repeated 10 times should be collapsed
        # Build evidence that is clearly >3000 chars with lots of repetition
        repeated_line = "AssertionError: expected True got False"
        filler = "some unrelated noise padding line which adds length\n" * 80
        evidence = (repeated_line + "\n") * 10 + filler
        assert len(evidence) > 3000  # sanity check
        result = EvidenceCompactor.compact_v2(evidence, limit=3000)
        # Dedup should collapse the 10 identical lines to 1
        count = result.count(repeated_line)
        assert count <= 1  # deduplicated to single occurrence

    def test_compact_v2_prioritizes_assertion_over_noise(self):
        # The assertion line should survive even with a small limit
        noise = "random noise line " * 200
        assertion = "AssertionError: value mismatch"
        evidence = noise + "\n" + assertion
        result = EvidenceCompactor.compact_v2(
            evidence, limit=300, anchor_symbol="value_check"
        )
        assert "AssertionError" in result

    def test_compact_v2_fallback_on_all_empty_lines(self):
        # Only whitespace lines after stripping
        evidence = "\n" * 500 + "actual error line"
        result = EvidenceCompactor.compact_v2(evidence, limit=3000)
        assert "actual error line" in result

    def test_compact_v2_no_regression_vs_v1(self):
        """compact_v2 must always return something non-empty for non-empty evidence."""
        evidence = self._make_long_evidence()
        result_v1 = EvidenceCompactor.compact(evidence, limit=500)
        result_v2 = EvidenceCompactor.compact_v2(evidence, limit=500)
        assert result_v2  # non-empty
        assert len(result_v2) <= 500


# ---------------------------------------------------------------------------
# MemoryRetrievalAdapter.retrieve_reranked
# ---------------------------------------------------------------------------

class _FakeLessonStore:
    """In-memory lesson store for testing."""

    def __init__(self, lessons: list[dict]) -> None:
        self._lessons = lessons

    def query(self, *, query_text: str, limit: int) -> list[dict]:
        return self._lessons[:limit]


class TestRetrieveReranked:
    def _make_adapter(self, lessons: list[dict]) -> MemoryRetrievalAdapter:
        store = _FakeLessonStore(lessons)
        return MemoryRetrievalAdapter(store=store, enabled=True)

    def _lesson(self, idx: int, summary: str, pattern_type: str = "success") -> dict:
        return {
            "lesson_id": f"lesson_{idx}",
            "summary": summary,
            "relevance_score": 1.0,
            "provenance": f"receipt_{idx}",
            "source": "test",
            "classification": "fix" if pattern_type == "success" else "fail",
        }

    def test_reranked_returns_limit(self):
        lessons = [self._lesson(i, f"summary about thing_{i}") for i in range(10)]
        adapter = self._make_adapter(lessons)
        result = adapter.retrieve_reranked(query_text="thing", limit=3)
        assert len(result) <= 3

    def test_reranked_boost_anchor_symbol(self):
        lessons = [
            self._lesson(0, "unrelated stuff here nothing useful"),
            self._lesson(1, "fix applies to write_output_format method"),
        ]
        adapter = self._make_adapter(lessons)
        result = adapter.retrieve_reranked(
            query_text="format", anchor_symbol="write_output_format", limit=2
        )
        assert result[0].finding_id == "lesson_1"  # anchor-boosted should rank first

    def test_reranked_failure_pattern_penalized(self):
        # Use different summaries to avoid deduplication collapsing them
        lessons = [
            self._lesson(0, "common fix approach for output rendering", pattern_type="failure"),
            self._lesson(1, "common fix approach for output formatting", pattern_type="success"),
        ]
        adapter = self._make_adapter(lessons)
        result = adapter.retrieve_reranked(query_text="common fix", limit=2)
        assert len(result) == 2
        # success should rank higher than failure for similar content
        success_idx = next(i for i, r in enumerate(result) if r.pattern_type == "success")
        failure_idx = next(i for i, r in enumerate(result) if r.pattern_type == "failure")
        assert success_idx < failure_idx

    def test_reranked_deduplication(self):
        """Near-identical summaries should be collapsed."""
        lessons = [
            self._lesson(0, "output formatting fix write render path"),
            self._lesson(1, "output formatting fix write render path"),  # near-duplicate
            self._lesson(2, "completely different lesson about import error"),
        ]
        adapter = self._make_adapter(lessons)
        result = adapter.retrieve_reranked(query_text="output formatting", limit=10)
        # Near-duplicate should be collapsed
        assert len(result) <= 2

    def test_reranked_summary_pruned_to_max_chars(self):
        long_summary = "x" * 2000
        lessons = [self._lesson(0, long_summary)]
        adapter = self._make_adapter(lessons)
        result = adapter.retrieve_reranked(query_text="x", limit=1, max_chars=800)
        assert len(result[0].summary) <= 800

    def test_reranked_empty_store_returns_empty(self):
        adapter = self._make_adapter([])
        result = adapter.retrieve_reranked(query_text="anything", limit=5)
        assert result == []

    def test_reranked_disabled_adapter_returns_empty(self):
        lessons = [self._lesson(0, "something")]
        adapter = MemoryRetrievalAdapter(store=_FakeLessonStore(lessons), enabled=False)
        result = adapter.retrieve_reranked(query_text="something", limit=5)
        assert result == []

    def test_reranked_metadata_populated(self):
        lessons = [self._lesson(0, "some lesson")]
        adapter = self._make_adapter(lessons)
        result = adapter.retrieve_reranked(query_text="lesson", anchor_symbol="my_sym", limit=1)
        # retrieve_reranked sets metadata AFTER calling retrieve internally;
        # validate the rerank-specific fields are present.
        assert "rerank_accepted" in adapter.last_metadata
        assert adapter.last_metadata["rerank_accepted"] == len(result)
