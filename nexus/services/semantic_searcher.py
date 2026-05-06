from __future__ import annotations

import logging
from typing import Any, Dict, List

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
        try:
            rows = self.repository.search_fts(
                table_name=table_name,
                query=query,
                limit=limit,
                fallback_columns=fallback_columns or ["condition", "action"],
            )
        except Exception as exc:
            logger.error("Semantic search failed on %s: %s", table_name, exc)
            return []
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
