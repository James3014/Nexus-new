from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Dict, List

from nexus.contracts.retrieval_receipt import build_retrieval_receipt

logger = logging.getLogger(__name__)


class SemanticSearcher:
    """Service-layer search seam over memory repositories."""

    def __init__(self, repository: Any):
        self.repository = repository

    def search(
        self,
        query: str,
        table_name: str = "policy",
        limit: int = 3,
        fallback_columns: List[str] | None = None,
    ) -> List[Dict[str, Any]]:
        rows = self._search_rows(
            query=query,
            table_name=table_name,
            limit=limit,
            fallback_columns=fallback_columns,
        )
        if rows is None or getattr(rows, "empty", True):
            return []

        reminders: List[Dict[str, Any]] = []
        for _, row in rows.iterrows():
            score = float(getattr(row, "_score", 1.0))
            rule_id = str(row.get("rule_id", "unknown"))
            confidence = row.get("confidence", row.get("belief_confidence", score))
            reminders.append(
                {
                    "id": rule_id,
                    "content": str(row.get("action", row.get("condition", "No Content"))),
                    "relevance": round(min(1.0, score), 2),
                    "confidence": round(max(0.0, min(1.0, float(confidence or 0.0))), 2),
                    "confidence_source": "row" if "confidence" in row.index or "belief_confidence" in row.index else "search_score",
                    "evidence_ref": f"semantic:{table_name}:{rule_id}",
                    "source": "lancedb-fts" if "_score" in row.index else "lancedb-fallback",
                }
            )
        return reminders

    def build_retrieval_receipt(
        self,
        query: str,
        table_name: str = "policy",
        limit: int = 3,
        fallback_columns: List[str] | None = None,
        index_snapshot_id: str | None = None,
    ) -> Dict[str, Any]:
        rows = self._search_rows(
            query=query,
            table_name=table_name,
            limit=limit,
            fallback_columns=fallback_columns,
        )
        if rows is None or getattr(rows, "empty", True):
            return build_retrieval_receipt(
                query=query,
                index_snapshot_id=index_snapshot_id or f"memory_index:{table_name}:0:unknown",
                chunk_hash_version="sha256:v1",
                results=[],
            )
        results: list[dict[str, Any]] = []
        for idx, row in rows.iterrows():
            rule_id = str(row.get("record_id", row.get("rule_id", f"semantic:{table_name}:{idx}")))
            score_components = _score_components(row, idx=idx)
            results.append(
                {
                    "source_id": rule_id,
                    "source_path": str(row.get("source_path", row.get("_source_table", table_name))),
                    "selected": True,
                    "selected_reason": "returned_by_semantic_search",
                    "score_components": score_components,
                    "chunk_hash": _chunk_hash(row),
                }
            )
        return build_retrieval_receipt(
            query=query,
            index_snapshot_id=index_snapshot_id or _snapshot_id(table_name, rows),
            chunk_hash_version="sha256:v1",
            results=results,
        )

    def _search_rows(
        self,
        *,
        query: str,
        table_name: str,
        limit: int,
        fallback_columns: List[str] | None,
    ) -> Any:
        try:
            return self.repository.search_fts(
                table_name=table_name,
                query=query,
                limit=limit,
                fallback_columns=fallback_columns or ["condition", "action"],
            )
        except Exception as exc:
            logger.error("Semantic search failed on %s: %s", table_name, exc)
            return None


def _score_components(row: Any, *, idx: int) -> dict[str, float]:
    if "_score" in row.index:
        return {"fts": float(row.get("_score", 0.0))}
    return {"fallback_rank": round(1.0 / float(idx + 1), 6)}


def _snapshot_id(table_name: str, rows: Any) -> str:
    row_count = len(rows.index) if hasattr(rows, "index") else 0
    updated_values = []
    for column in ("updated_at", "last_updated", "timestamp"):
        if column in getattr(rows, "columns", []):
            updated_values = [str(value) for value in rows[column].dropna().tolist()]
            break
    latest = max(updated_values) if updated_values else "unknown"
    return f"memory_index:{table_name}:{row_count}:{latest}"


def _chunk_hash(row: Any) -> str:
    payload = {
        key: row.get(key, "")
        for key in ("payload_json", "content", "action", "condition", "evidence_ref")
        if key in row.index
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()
