from __future__ import annotations

import math
import os
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
        self._embedding_store: dict[str, list[float]] = {}

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


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class RealEvoEmbeddingIndex(EvoEmbeddingIndex):
    def __init__(self, index_path: str = ".nexus/knowledge/evo_index") -> None:
        super().__init__(index_path)
        self._model_name = os.environ.get("NEXUS_EMBEDDING_MODEL", "").strip()
        self._model = None
        self._model_available = bool(self._model_name)

    def add(self, receipt_id: str, content: str, timestamp: float) -> None:
        super().add(receipt_id, content, timestamp)
        if self._model_available:
            embedding = self._encode(content)
            if embedding:
                self._embedding_store[receipt_id] = embedding

    def query(self, query: str, top_k: int = 5) -> list[SearchResult]:
        if not self._model_available:
            return super().query(query, top_k)
        try:
            query_emb = self._encode(query)
            if not query_emb:
                return super().query(query, top_k)
            scored: list[tuple[str, str, float]] = []
            for rid, (content, _) in self._store.items():
                emb = self._embedding_store.get(rid)
                if emb:
                    score = _cosine_similarity(query_emb, emb)
                else:
                    score = 0.0
                scored.append((rid, content, score))
            scored.sort(key=lambda x: x[2], reverse=True)
            return [
                SearchResult(receipt_id=rid, content=content, score=score)
                for rid, content, score in scored[:top_k]
            ]
        except Exception:
            return super().query(query, top_k)

    def _encode(self, text: str) -> list[float] | None:
        try:
            if self._model is None:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self._model_name)
            emb = self._model.encode(text, normalize_embeddings=True)
            return emb.tolist()
        except Exception:
            return None
