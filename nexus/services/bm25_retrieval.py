"""Shared tokenised Okapi BM25 scoring for Nexus retrieval surfaces (#2640).

One implementation backs CodeIntel file ranking, the DCI locator, FindingsMemoryStore.search
and the MemoryRepository.search_fts fallback, so every surface ranks text the same way.

The tokenizer and the scoring formula follow the baseline frozen in the #2626 preregistration
(knowledge ``nexus/research/2026-10-18-layer1-L2-active-memory``, PREREG sha prefix
``91aa5c9c55056b47``): tokens are ``[A-Za-z_][A-Za-z0-9_]*`` lower-cased; each token is also
split on ``_`` and camelCase into parts of length >= 3 (parts are added only when the split
yields something other than the whole token); k1 = 1.2, b = 0.75; IDF is the non-negative
Lucene form ``ln((N - n + 0.5) / (n + 0.5) + 1)``. Only documents with a positive score are
returned; ties keep insertion order, so callers that insert documents sorted by id get
id-ascending ties.

Pure Python, no I/O, no model calls.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Hashable, Iterable, Sequence

__all__ = ["BM25Index", "bm25_rank", "bm25_tokens"]

_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_CAMEL_PART_RE = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|[0-9]+")


def bm25_tokens(text: str) -> list[str]:
    """Tokenise ``text`` exactly like the preregistered BM25 baseline."""
    out: list[str] = []
    for token in _TOKEN_RE.findall(text or ""):
        lowered = token.lower()
        out.append(lowered)
        parts: list[str] = []
        for piece in token.split("_"):
            parts.extend(_CAMEL_PART_RE.findall(piece))
        parts = [part.lower() for part in parts if len(part) >= 3]
        if len(parts) > 1 or (parts and parts[0] != lowered):
            out.extend(parts)
    return out


class BM25Index:
    """In-memory Okapi BM25 index over ``(doc_id, text)`` pairs."""

    def __init__(
        self, docs: Iterable[tuple[Hashable, str]], *, k1: float = 1.2, b: float = 0.75
    ) -> None:
        self.ids: list[Hashable] = []
        self._tf: list[Counter[str]] = []
        self._len: list[int] = []
        df: Counter[str] = Counter()
        for doc_id, text in docs:
            counts = Counter(bm25_tokens(text))
            self.ids.append(doc_id)
            self._tf.append(counts)
            self._len.append(sum(counts.values()))
            df.update(counts.keys())
        self.n_docs = len(self.ids)
        self._avg_len = (sum(self._len) / self.n_docs) if self.n_docs else 0.0
        self._idf = {
            term: math.log((self.n_docs - n + 0.5) / (n + 0.5) + 1.0) for term, n in df.items()
        }
        self.k1 = k1
        self.b = b
        self._postings: dict[str, list[int]] = {}
        for index, counts in enumerate(self._tf):
            for term in counts:
                self._postings.setdefault(term, []).append(index)

    def __len__(self) -> int:
        return self.n_docs

    def scores(self, query: str) -> dict[int, float]:
        """Return ``{doc_index: score}`` for every document with a positive score."""
        if not self.n_docs or self._avg_len <= 0:
            return {}
        query_counts = Counter(bm25_tokens(query))
        totals: dict[int, float] = {}
        for term, query_freq in query_counts.items():
            idf = self._idf.get(term)
            if idf is None:
                continue
            for index in self._postings[term]:
                freq = self._tf[index][term]
                denom = freq + self.k1 * (1 - self.b + self.b * self._len[index] / self._avg_len)
                totals[index] = (
                    totals.get(index, 0.0) + query_freq * idf * freq * (self.k1 + 1) / denom
                )
        return {index: score for index, score in totals.items() if score > 0}

    def rank(self, query: str, limit: int | None = None) -> list[tuple[Hashable, float]]:
        """Return ``[(doc_id, score)]`` sorted by score desc, ties in insertion order."""
        ordered = sorted(self.scores(query).items(), key=lambda item: (-item[1], item[0]))
        if limit is not None and limit >= 0:
            ordered = ordered[:limit]
        return [(self.ids[index], score) for index, score in ordered]


def bm25_rank(
    docs: Sequence[tuple[Hashable, str]], query: str, *, limit: int | None = None
) -> list[tuple[Hashable, float]]:
    """One-shot helper: build an index over ``docs`` and rank ``query``."""
    return BM25Index(docs).rank(query, limit=limit)
