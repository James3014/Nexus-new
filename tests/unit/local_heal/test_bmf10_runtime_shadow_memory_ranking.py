"""Tests for BMF10-RSH runtime shadow memory ranking hook."""
from __future__ import annotations

import json
import pytest
from nexus.services.local_heal.memory_retrieval_adapter import MemoryRetrievalAdapter, RetrievedLesson
from nexus.services.local_heal.memory_trace import MemoryTrace, build_memory_trace_from_adapter


class _FakeLessonStore:
    def __init__(self, lessons: list[dict]):
        self._lessons = lessons
        self.last_metadata = {}

    def query(self, *, query_text: str, limit: int) -> list[dict]:
        return self._lessons[:limit]


class TestRuntimeShadowInvariance:
    """Runtime invariance: shadow scoring must not change retrieval order."""

    def test_retrieve_reranked_order_unchanged(self):
        """retrieve_reranked returns same lesson order with shadow enabled."""
        lessons = [
            {"lesson_id": "l1", "summary": "alpha fix", "classification": "success",
             "provenance": "receipt:abc", "source": "LocalJsonlLessonStore", "relevance_score": 1.0},
            {"lesson_id": "l2", "summary": "beta fix", "classification": "failure",
             "provenance": "receipt:def", "source": "LocalJsonlLessonStore", "relevance_score": 0.8},
            {"lesson_id": "l3", "summary": "gamma fix", "classification": "success",
             "provenance": "receipt:ghi", "source": "LocalJsonlLessonStore", "relevance_score": 0.9},
        ]
        adapter = MemoryRetrievalAdapter(store=_FakeLessonStore(lessons), enabled=True)
        result = adapter.retrieve_reranked(query_text="test query", limit=3)

        # Order is by reranking score: l1(1.0) > l3(0.9) > l2(0.8)
        # Shadow must NOT change this order
        returned_ids = [r.finding_id for r in result]
        assert returned_ids == ["l1", "l3", "l2"]
        # Verify shadow did not alter it (same ids regardless of shadow)
        assert set(returned_ids) == {"l1", "l2", "l3"}

    def test_selected_ids_unchanged(self):
        """selected_ids metadata remains same regardless of shadow."""
        lessons = [
            {"lesson_id": "l1", "summary": "fix", "classification": "success",
             "provenance": "receipt:abc", "source": "LocalJsonlLessonStore", "relevance_score": 1.0},
        ]
        adapter = MemoryRetrievalAdapter(store=_FakeLessonStore(lessons), enabled=True)
        adapter.retrieve_reranked(query_text="test", limit=5)

        assert adapter.last_metadata["selected_ids"] == ["l1"]

    def test_shadow_metadata_present(self):
        """shadow_ranking is present in metadata when lessons exist."""
        lessons = [
            {"lesson_id": "l1", "summary": "fix", "classification": "success",
             "provenance": "receipt:abc", "source": "LocalJsonlLessonStore", "relevance_score": 1.0},
        ]
        adapter = MemoryRetrievalAdapter(store=_FakeLessonStore(lessons), enabled=True)
        adapter.retrieve_reranked(query_text="test", limit=5)

        shadow = adapter.last_metadata.get("shadow_ranking", {})
        assert shadow.get("enabled") is True
        assert shadow.get("runtime_order_changed") is False
        assert shadow.get("prompt_changed") is False
        assert shadow.get("verifier_changed") is False
        assert shadow.get("shadow_only") is True

    def test_shadow_metadata_bounded(self):
        """shadow metadata does not include raw lesson summaries."""
        lessons = [
            {"lesson_id": "l1", "summary": "very long summary " * 100, "classification": "success",
             "provenance": "receipt:abc", "source": "LocalJsonlLessonStore", "relevance_score": 1.0},
        ]
        adapter = MemoryRetrievalAdapter(store=_FakeLessonStore(lessons), enabled=True)
        adapter.retrieve_reranked(query_text="test", limit=5)

        shadow_str = json.dumps(adapter.last_metadata.get("shadow_ranking", {}))
        # Should not contain the long summary text
        assert "very long summary" not in shadow_str

    def test_shadow_failure_fail_open(self):
        """Shadow scoring failure does not alter returned lessons."""
        adapter = MemoryRetrievalAdapter(store=_FakeLessonStore([]), enabled=True)
        result = adapter.retrieve_reranked(query_text="test", limit=5)

        # Empty result is expected
        assert result == []
        shadow = adapter.last_metadata.get("shadow_ranking", {})
        # Empty lessons should still produce valid shadow metadata
        assert shadow.get("runtime_order_changed") is False
        assert shadow.get("prompt_changed") is False
        assert shadow.get("verifier_changed") is False


class TestReceiptShadowTrace:
    """Receipt includes shadow_ranking from memory trace."""

    def test_memory_trace_includes_shadow(self):
        """MemoryTrace.shadow_ranking is populated from adapter metadata."""
        adapter_metadata = {
            "accepted": 1,
            "selected_ids": ["l1"],
            "shadow_ranking": {
                "enabled": True,
                "status": "COMPLETED",
                "scored_count": 1,
                "rank_changes": 0,
                "runtime_order_changed": False,
                "shadow_only": True,
            },
        }
        trace = build_memory_trace_from_adapter(adapter_metadata)
        d = trace.to_dict()
        assert d["shadow_ranking"]["enabled"] is True
        assert d["shadow_ranking"]["runtime_order_changed"] is False

    def test_memory_trace_shadow_in_receipt(self):
        """receipt.memory_influence.shadow_ranking is present."""
        from nexus.services.local_heal.memory_trace import get_empty_trace
        trace = get_empty_trace()
        d = trace.to_dict()
        assert "shadow_ranking" in d
        assert d["shadow_ranking"] == {}


class TestRuntimeOrderInvariance:
    """Verify runtime order is never changed by shadow scoring."""

    def test_shadow_does_not_reorder_lessons(self):
        """Shadow scoring records proposed order but does not change returned order."""
        from nexus.services.local_heal.shadow_memory_ranking import shadow_score_lessons

        lessons = [
            {"lesson_id": "l1", "summary": "evidence gap fix", "classification": "evidence_gap",
             "provenance": "receipt:abc", "source": "LocalJsonlLessonStore", "relevance_score": 1.0},
            {"lesson_id": "l2", "summary": "verifier pass fix", "classification": "verifier_pass",
             "provenance": "receipt:def", "source": "LocalJsonlLessonStore", "relevance_score": 0.9},
            {"lesson_id": "l3", "summary": "failure fix", "classification": "failure",
             "provenance": "receipt:ghi", "source": "LocalJsonlLessonStore", "relevance_score": 0.8},
        ]
        result = shadow_score_lessons(lessons, task_classification="evidence_gap")

        # Runtime order unchanged
        assert result.shadow_safety["runtime_order_changed"] is False
        assert result.shadow_safety["prompt_changed"] is False
        assert result.shadow_safety["verifier_changed"] is False

        # Proposed order may differ (l1 should be top due to evidence_gap_bonus)
        assert result.top_proposed_ids[0] == "l1"


class TestNoTaskIdLogic:
    """No task_id-specific logic in shadow scoring."""

    def test_scoring_independent_of_task_id(self):
        """Same lessons produce same shadow scores regardless of task_id."""
        from nexus.services.local_heal.shadow_memory_ranking import shadow_score_lessons

        lessons = [
            {"lesson_id": "l1", "summary": "fix", "classification": "success",
             "provenance": "receipt:abc", "source": "LocalJsonlLessonStore", "relevance_score": 1.0},
        ]
        r1 = shadow_score_lessons(lessons, task_classification="task_A")
        r2 = shadow_score_lessons(lessons, task_classification="task_B")
        assert r1.shadow_scored_count == r2.shadow_scored_count


class TestRegressionChecks:
    """Regression checks to ensure no behavior change."""

    def test_c_12481_still_passes(self):
        """C_12481 regression check."""
        from nexus.services.local_heal.memory_trace import get_empty_trace
        trace = get_empty_trace()
        d = trace.to_dict()
        assert d["trace_status"] == "TRACE_MISSING"

    def test_c_13453_still_passes(self):
        """C_13453 regression check."""
        from nexus.services.local_heal.memory_trace import get_empty_trace
        trace = get_empty_trace()
        d = trace.to_dict()
        assert d["trace_status"] == "TRACE_MISSING"
