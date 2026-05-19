from __future__ import annotations

from nexus.contracts.hybrid_retrieval import build_hybrid_retrieval_query, fuse_hybrid_retrieval_results


def test_hybrid_retrieval_selects_top_k_with_explainable_scores() -> None:
    query = build_hybrid_retrieval_query(
        query="context receipt boundary",
        index_snapshot_id="memory:policy:2:2026-05-20",
        chunk_hash_version="sha256:v1",
        top_k=1,
    )

    payload = fuse_hybrid_retrieval_results(
        query,
        [
            {
                "source_id": "a",
                "source_path": "docs/a.md",
                "chunk_hash": "sha256:a",
                "bm25": 0.2,
                "dense": 0.9,
            },
            {
                "source_id": "b",
                "source_path": "docs/b.md",
                "chunk_hash": "sha256:b",
                "bm25": 0.8,
                "dense": 0.1,
            },
        ],
    )

    assert payload["status"] == "PASS"
    assert payload["selected_count"] == 1
    assert payload["results"][0]["source_id"] == "a"
    assert payload["results"][0]["selected_reason"] == "top_k_hybrid_fusion"
    assert payload["retrieval_receipt"]["status"] == "PASS"
    assert payload["runtime_update_allowed"] is False
    assert payload["public_benchmark_allowed"] is False


def test_hybrid_retrieval_returns_when_candidate_lacks_hash_or_scores() -> None:
    query = build_hybrid_retrieval_query(
        query="context receipt boundary",
        index_snapshot_id="memory:policy:1:2026-05-20",
        chunk_hash_version="sha256:v1",
    )

    payload = fuse_hybrid_retrieval_results(
        query,
        [{"source_id": "a", "source_path": "docs/a.md", "dense": 0.4}],
    )

    assert payload["status"] == "RETURN"
    assert "candidate_0:missing_chunk_hash" in payload["blockers"]
    assert "candidate_0:missing_bm25_score" in payload["blockers"]
    assert payload["selected_count"] == 0
