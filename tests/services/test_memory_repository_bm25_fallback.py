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


def test_search_fts_without_fallback_columns_has_no_fallback(tmp_path):
    """#2640 review F1: no fallback columns keeps the old "no FTS index -> empty" rule."""
    repo = _repo(tmp_path)
    repo.add_rows("t", [{"id": "x", "content": "quantum retry failed with error"}])
    assert repo.search_fts("t", "quantum retry").empty
    assert repo.search_fts_across_tables("quantum retry", ["t"], limit=3).empty


def test_search_fts_fallback_applies_relevance_floor(tmp_path):
    repo = _repo(tmp_path)
    repo.add_rows(
        "t",
        [
            {
                "id": f"c{i}",
                "content": f"LocalHeal lesson {i}: verifier failed with error in module",
            }
            for i in range(6)
        ]
        + [{"id": "hit", "content": "websocket reconnect timeout race in coordinator"}],
    )
    generic = repo.search_fts(
        "t", "the test fails with an error in the module", fallback_columns=["content"]
    )
    assert generic.empty
    specific = repo.search_fts("t", "coordinator websocket timeout", fallback_columns=["content"])
    assert list(specific["id"]) == ["hit"]


def test_bm25_frame_search_edge_cases():
    df = pd.DataFrame([{"a": "alpha"}, {"a": "beta"}])
    assert bm25_frame_search(df, "", limit=3).empty
    assert bm25_frame_search(df, "gamma", limit=3).empty
    assert bm25_frame_search(df, "alpha", columns=["missing"]).empty
    assert list(bm25_frame_search(df, "beta", columns=["a"]).index) == [1]
    assert list(bm25_frame_search(df, "beta").index) == [1]  # columns=None: every string column
