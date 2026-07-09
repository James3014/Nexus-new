from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SearchResult:
    receipt_id: str
    content: str
    score: float


class EvoEmbeddingIndex:
    def __init__(self, index_path: str = ".nexus/knowledge/evo_index") -> None:
        self._index_path = index_path
        self._store: dict[str, tuple[str, float]] = {}

    def add(self, receipt_id: str, content: str, timestamp: float) -> None:
        self._store[receipt_id] = (content, timestamp)

    def query(self, query: str, top_k: int = 5) -> list[SearchResult]:
        query_tokens = set(query.lower().split())
        scored: list[tuple[str, str, float]] = []
        for rid, (content, _) in self._store.items():
            content_tokens = set(content.lower().split())
            if not query_tokens or not content_tokens:
                score = 0.0
            else:
                intersection = query_tokens & content_tokens
                union = query_tokens | content_tokens
                score = len(intersection) / len(union)
            scored.append((rid, content, score))
        scored.sort(key=lambda x: x[2], reverse=True)
        return [
            SearchResult(receipt_id=rid, content=content, score=score)
            for rid, content, score in scored[:top_k]
        ]
