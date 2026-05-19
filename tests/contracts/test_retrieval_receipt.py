from __future__ import annotations

from nexus.contracts.retrieval_receipt import (
    RETRIEVAL_RECEIPT_SCHEMA,
    RetrievalReceipt,
    RetrievalResultReceipt,
    build_retrieval_receipt,
    validate_retrieval_receipt,
)


def test_retrieval_receipt_records_scores_snapshot_and_selection_reasons() -> None:
    payload = build_retrieval_receipt(
        query="route DAG evidence boundary",
        index_snapshot_id="lancedb-snapshot-2026-05-20",
        chunk_hash_version="sha256:v1",
        results=[
            {
                "source_id": "adr-routing",
                "source_path": "docs/plans/ADR.md",
                "selected": True,
                "selected_reason": "highest_fusion_score",
                "score_components": {"bm25": 0.4, "dense": 0.7, "fusion": 0.82},
                "chunk_hash": "sha256:abc",
            },
            {
                "source_id": "old-note",
                "source_path": "docs/archive/old.md",
                "selected": False,
                "not_selected_reason": "below_threshold",
                "score_components": {"bm25": 0.1, "dense": 0.2, "fusion": 0.18},
                "chunk_hash": "sha256:def",
            },
        ],
    )

    assert payload["schema"] == RETRIEVAL_RECEIPT_SCHEMA
    assert payload["status"] == "PASS"
    assert payload["index_snapshot_id"] == "lancedb-snapshot-2026-05-20"
    assert payload["chunk_hash_version"] == "sha256:v1"
    assert payload["result_count"] == 2
    assert payload["selected_count"] == 1
    assert payload["results"][0]["selected_reason"] == "highest_fusion_score"
    assert payload["results"][1]["selected_reason"] == "below_threshold"
    assert payload["blockers"] == []
    assert "Retrieval receipts explain selection and scoring only." in payload["claim_boundary"]


def test_retrieval_receipt_returns_blockers_for_missing_snapshot_or_scores() -> None:
    payload = build_retrieval_receipt(
        query="route DAG evidence boundary",
        index_snapshot_id="",
        chunk_hash_version="sha256:v1",
        results=[
            {
                "source_id": "adr-routing",
                "source_path": "docs/plans/ADR.md",
                "selected": True,
                "selected_reason": "highest_fusion_score",
            }
        ],
    )

    assert payload["status"] == "RETURN"
    assert payload["blockers"] == [
        "missing_index_snapshot_id",
        "result_0:missing_score_components",
    ]


def test_validate_retrieval_receipt_accepts_dataclass_without_recursion() -> None:
    receipt = RetrievalReceipt(
        query="claim gate read model",
        index_snapshot_id="snapshot-1",
        chunk_hash_version="sha256:v1",
        results=[
            RetrievalResultReceipt(
                source_id="claim-gate",
                source_path="docs/plans/claim.md",
                selected=True,
                selected_reason="exact_title_match",
                score_components={"dense": 0.91},
            )
        ],
    )

    assert validate_retrieval_receipt(receipt) == []
    assert receipt.to_dict()["blockers"] == []
