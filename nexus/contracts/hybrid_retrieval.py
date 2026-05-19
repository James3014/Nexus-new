from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from nexus.contracts.retrieval_receipt import build_retrieval_receipt


HYBRID_RETRIEVAL_QUERY_SCHEMA = "nexus.hybrid_retrieval_query.v1"
HYBRID_RETRIEVAL_RESULT_SCHEMA = "nexus.hybrid_retrieval_result.v1"


@dataclass(frozen=True)
class HybridRetrievalQuery:
    query: str
    index_snapshot_id: str
    chunk_hash_version: str
    bm25_weight: float = 0.45
    dense_weight: float = 0.55
    top_k: int = 5
    schema: str = HYBRID_RETRIEVAL_QUERY_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        blockers = _query_blockers(self)
        return {
            "schema": self.schema,
            "status": "PASS" if not blockers else "RETURN",
            "query": self.query,
            "index_snapshot_id": self.index_snapshot_id,
            "chunk_hash_version": self.chunk_hash_version,
            "bm25_weight": self.bm25_weight,
            "dense_weight": self.dense_weight,
            "top_k": self.top_k,
            "blockers": blockers,
            "claim_boundary": [
                "Hybrid retrieval ranks candidate context only.",
                "It does not decide delivery, route quality, runtime promotion, or public readiness.",
            ],
        }


def build_hybrid_retrieval_query(
    *,
    query: str,
    index_snapshot_id: str,
    chunk_hash_version: str,
    bm25_weight: float = 0.45,
    dense_weight: float = 0.55,
    top_k: int = 5,
) -> dict[str, Any]:
    return HybridRetrievalQuery(
        query=query,
        index_snapshot_id=index_snapshot_id,
        chunk_hash_version=chunk_hash_version,
        bm25_weight=float(bm25_weight),
        dense_weight=float(dense_weight),
        top_k=int(top_k),
    ).to_dict()


def fuse_hybrid_retrieval_results(
    query_receipt: Mapping[str, Any],
    candidates: list[Mapping[str, Any]],
) -> dict[str, Any]:
    blockers = list(query_receipt.get("blockers", []) or [])
    scored = [_score_candidate(candidate, query_receipt=query_receipt) for candidate in candidates]
    for index, candidate in enumerate(scored):
        for blocker in candidate.pop("_blockers"):
            blockers.append(f"candidate_{index}:{blocker}")
    top_k = max(0, int(query_receipt.get("top_k") or 0))
    ranked = sorted(scored, key=lambda item: item["score_components"]["fusion"], reverse=True)
    selected_ids = {item["source_id"] for item in ranked[:top_k]}
    results: list[dict[str, Any]] = []
    for rank, item in enumerate(ranked, start=1):
        selected = item["source_id"] in selected_ids and not blockers
        item["selected"] = selected
        item["selected_reason"] = "top_k_hybrid_fusion" if selected else f"rank_{rank}_outside_top_k_or_blocked"
        results.append(item)
    receipt = build_retrieval_receipt(
        query=str(query_receipt.get("query") or ""),
        index_snapshot_id=str(query_receipt.get("index_snapshot_id") or ""),
        chunk_hash_version=str(query_receipt.get("chunk_hash_version") or ""),
        results=results,
    )
    blockers.extend(receipt.get("blockers", []) or [])
    return {
        "schema": HYBRID_RETRIEVAL_RESULT_SCHEMA,
        "status": "PASS" if not blockers else "RETURN",
        "query_receipt": dict(query_receipt),
        "candidate_count": len(candidates),
        "selected_count": sum(1 for item in results if item["selected"]),
        "results": results,
        "retrieval_receipt": receipt,
        "blockers": sorted(set(str(item) for item in blockers)),
        "runtime_update_allowed": False,
        "public_benchmark_allowed": False,
        "claim_boundary": [
            "Hybrid retrieval evidence is explainability input for context selection.",
            "The downstream claim gate must consume sealed evidence before any public or runtime claim.",
        ],
    }


def _query_blockers(query: HybridRetrievalQuery) -> list[str]:
    blockers: list[str] = []
    if not query.query.strip():
        blockers.append("missing_query")
    if not query.index_snapshot_id.strip():
        blockers.append("missing_index_snapshot_id")
    if not query.chunk_hash_version.strip():
        blockers.append("missing_chunk_hash_version")
    if query.top_k <= 0:
        blockers.append("invalid_top_k")
    if query.bm25_weight < 0 or query.dense_weight < 0:
        blockers.append("negative_weight")
    if query.bm25_weight == 0 and query.dense_weight == 0:
        blockers.append("zero_total_weight")
    return sorted(set(blockers))


def _score_candidate(candidate: Mapping[str, Any], *, query_receipt: Mapping[str, Any]) -> dict[str, Any]:
    blockers: list[str] = []
    source_id = str(candidate.get("source_id") or "")
    source_path = str(candidate.get("source_path") or "")
    chunk_hash = str(candidate.get("chunk_hash") or "")
    bm25 = _float_score(candidate.get("bm25_score", candidate.get("bm25")))
    dense = _float_score(candidate.get("dense_score", candidate.get("dense")))
    if not source_id:
        blockers.append("missing_source_id")
    if not source_path:
        blockers.append("missing_source_path")
    if not chunk_hash:
        blockers.append("missing_chunk_hash")
    if bm25 is None:
        blockers.append("missing_bm25_score")
        bm25 = 0.0
    if dense is None:
        blockers.append("missing_dense_score")
        dense = 0.0
    bm25_weight = float(query_receipt.get("bm25_weight") or 0.0)
    dense_weight = float(query_receipt.get("dense_weight") or 0.0)
    total_weight = bm25_weight + dense_weight
    fusion = 0.0 if total_weight <= 0 else ((bm25 * bm25_weight) + (dense * dense_weight)) / total_weight
    return {
        "source_id": source_id,
        "source_path": source_path,
        "chunk_hash": chunk_hash,
        "score_components": {
            "bm25": round(bm25, 6),
            "dense": round(dense, 6),
            "fusion": round(fusion, 6),
        },
        "_blockers": blockers,
    }


def _float_score(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
