from __future__ import annotations

from nexus.knowledge.evo_embedding_index import EvoEmbeddingIndex, SearchResult


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
