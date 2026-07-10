from __future__ import annotations

import os
from unittest.mock import patch

from nexus.knowledge.evo_embedding_index import (
    EvoEmbeddingIndex,
    RealEvoEmbeddingIndex,
    SearchResult,
    _cosine_similarity,
)


class TestEvoEmbeddingIndex:

    def test_evo_embedding_index_add_stores_in_memory(self):
        idx = EvoEmbeddingIndex()
        idx.add("receipt-1", "fix null pointer bug", 1000.0)
        results = idx.query("null pointer")
        assert len(results) == 1
        assert results[0].receipt_id == "receipt-1"

    def test_evo_embedding_index_query_returns_top_k(self):
        idx = EvoEmbeddingIndex()
        for i in range(10):
            idx.add(f"receipt-{i}", f"fix bug number {i}", float(i))
        results = idx.query("fix bug", top_k=3)
        assert len(results) == 3

    def test_evo_embedding_index_score_is_deterministic(self):
        idx = EvoEmbeddingIndex()
        idx.add("r1", "hello world foo bar", 1.0)
        r1 = idx.query("hello world")
        r2 = idx.query("hello world")
        assert r1[0].score == r2[0].score

    def test_evo_embedding_index_no_network_call(self, monkeypatch):
        import urllib.request
        original = urllib.request.urlopen
        called = False

        def fail(*args, **kwargs):
            nonlocal called
            called = True
            raise RuntimeError("should not be called")

        monkeypatch.setattr("urllib.request.urlopen", fail)
        idx = EvoEmbeddingIndex()
        idx.add("r1", "content", 1.0)
        results = idx.query("content")
        assert len(results) == 1
        assert not called

    def test_evo_embedding_index_search_result_frozen(self):
        result = SearchResult(receipt_id="r1", content="test", score=0.5)
        import pytest
        with pytest.raises(Exception):
            result.score = 0.9

    # === L3-C: real EvoEmbedding ===

    def test_real_evo_embedding_disabled_uses_jaccard(self):
        if "NEXUS_EMBEDDING_MODEL" in os.environ:
            del os.environ["NEXUS_EMBEDDING_MODEL"]
        idx = RealEvoEmbeddingIndex()
        idx.add("r1", "fix null pointer bug", 1.0)
        results = idx.query("null pointer")
        assert len(results) == 1
        # Jaccard score should be > 0 for matching token
        assert results[0].score > 0.0

    def test_real_evo_embedding_fallback_on_error(self):
        os.environ["NEXUS_EMBEDDING_MODEL"] = "all-MiniLM-L6-v2"
        idx = RealEvoEmbeddingIndex()
        # Without mock, model won't load -> fallback to Jaccard
        idx.add("r1", "some content", 1.0)
        results = idx.query("some")
        assert len(results) == 1
        assert results[0].score > 0.0
        del os.environ["NEXUS_EMBEDDING_MODEL"]

    def test_cosine_similarity_basic(self):
        a = [1.0, 0.0, 0.0]
        b = [1.0, 0.0, 0.0]
        assert _cosine_similarity(a, b) == 1.0

    def test_cosine_similarity_orthogonal(self):
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert _cosine_similarity(a, b) == 0.0

    def test_cosine_similarity_empty(self):
        assert _cosine_similarity([], []) == 0.0
