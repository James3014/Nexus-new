"""MemoryRepository.search_fts fallback uses tokenised BM25 (#2640)."""

from __future__ import annotations

import pandas as pd
import pytest

from nexus.services.memory_repository import (
    MemoryRepository,
    NoEmbeddingProvider,
    bm25_frame_search,
)

pytest.importorskip("lancedb")


def _repo(tmp_path):
    return MemoryRepository(tmp_path / "db", embedding_provider=NoEmbeddingProvider())


def test_search_fts_fallback_ranks_sentence_query(tmp_path):
    repo = _repo(tmp_path)
    repo.add_rows(
        "items",
        [
            {
                "id": "a",
                "title": "lancedb fallback",
                "text": "search_fts falls back to substring match",
            },
            {"id": "b", "title": "gateway", "text": "deploy restart"},
            {
                "id": "c",
                "title": "fallback",
                "text": "lancedb lancedb fallback search_fts substring",
            },
        ],
    )
    frame = repo.search_fts(
        "items",
        "the search_fts substring fallback in LanceDB never matched",
        limit=5,
        fallback_columns=["title", "text"],
    )
    assert list(frame["id"]) == ["c", "a"]
    assert list(frame["_score"]) == sorted(frame["_score"], reverse=True)


def test_search_fts_skips_missing_fallback_columns_instead_of_keyerror(tmp_path):
    repo = _repo(tmp_path)
    repo.add_rows(
        "findings_cards",
        [{"id": "x", "title": "retry ladder", "body": "retry ladder bug", "content": "c"}],
    )
    frame = repo.search_fts(
        "findings_cards",
        "retry ladder",
        limit=5,
        fallback_columns=["title", "body", "content", "aaak_content"],
    )
    assert list(frame["id"]) == ["x"]


def test_search_fts_without_fallback_columns_uses_string_columns(tmp_path):
    repo = _repo(tmp_path)
    repo.add_rows("t", [{"id": "x", "note": "quantum retry"}, {"id": "y", "note": "other"}])
    assert list(repo.search_fts("t", "quantum")["id"]) == ["x"]


def test_bm25_frame_search_edge_cases():
    df = pd.DataFrame([{"a": "alpha"}, {"a": "beta"}])
    assert bm25_frame_search(df, "", limit=3).empty
    assert bm25_frame_search(df, "gamma", limit=3).empty
    assert bm25_frame_search(df, "alpha", columns=["missing"]).empty
    assert list(bm25_frame_search(df, "beta", columns=["a"]).index) == [1]
