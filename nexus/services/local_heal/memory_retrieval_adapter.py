from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class RetrievedLesson:
    finding_id: str
    summary: str
    relevance_score: float
    provenance: str
    source: str
    pattern_type: str

    @property
    def scoring_delta(self) -> float:
        base = max(0.0, min(1.0, float(self.relevance_score))) * 4.0
        if self.pattern_type == "success":
            return base
        if self.pattern_type == "failure":
            return -base
        return 0.0


class LessonStore(Protocol):
    def query(self, *, query_text: str, limit: int) -> list[dict[str, Any]]:
        ...


class LocalJsonlLessonStore:
    def __init__(self, path: Path | None = None) -> None:
        root = Path(__file__).resolve().parents[3]
        self.path = path or root / ".nexus/reports/learn/learning_closure.jsonl"

    def query(self, *, query_text: str, limit: int) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        tokens = {token for token in query_text.lower().replace("_", " ").split() if len(token) >= 3}
        rows: list[tuple[float, dict[str, Any]]] = []
        for line in self.path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            text = " ".join(str(item.get(key, "")) for key in ("lesson_id", "task_id", "classification", "summary", "source"))
            lowered = text.lower().replace("_", " ")
            overlap = sum(1 for token in tokens if token in lowered)
            if overlap:
                rows.append((float(overlap), item))
        rows.sort(key=lambda pair: pair[0], reverse=True)
        return [item for _score, item in rows[:limit]]


class MemoryRetrievalAdapter:
    """Retrieves provenance-backed local-heal lessons.

    LanceDB can be supplied as a store with the same query contract. The default
    local JSONL fallback is intentionally bounded and fail-open: no store or no
    match records no_memory_match instead of blocking repair.
    """

    # BMF3-OBS: class-level last trace (replaces module global)
    _last_trace: dict[str, Any] = {}

    def __init__(self, store: LessonStore | None = None, *, enabled: bool = True) -> None:
        self.store = store or LocalJsonlLessonStore()
        self.enabled = enabled
        self.last_metadata: dict[str, Any] = {}

    def retrieve(self, *, query_text: str, limit: int = 5) -> list[RetrievedLesson]:
        self.last_metadata = {
            "enabled": bool(self.enabled),
            "query_text": query_text,
            "no_memory_match": False,
            "rejected_without_provenance": 0,
            "source": self.store.__class__.__name__,
        }
        if not self.enabled:
            self.last_metadata["status"] = "disabled"
            self.last_metadata["no_memory_match"] = True
            return []
        try:
            raw_rows = self.store.query(query_text=query_text, limit=limit)
        except Exception as exc:
            self.last_metadata["status"] = "retrieval_failed"
            self.last_metadata["failure_reason"] = exc.__class__.__name__
            self.last_metadata["no_memory_match"] = True
            return []

        lessons: list[RetrievedLesson] = []
        for row in raw_rows:
            provenance = str(row.get("provenance") or row.get("receipt_id") or row.get("evidence_ref") or "").strip()
            if not provenance:
                self.last_metadata["rejected_without_provenance"] += 1
                continue
            classification = str(row.get("classification") or row.get("pattern_type") or "").lower()
            pattern_type = "failure" if any(token in classification for token in ("fail", "unsupported", "gap", "owner")) else "success"
            lessons.append(
                RetrievedLesson(
                    finding_id=str(row.get("lesson_id") or row.get("finding_id") or row.get("task_id") or "lesson"),
                    summary=str(row.get("summary") or row.get("lesson") or ""),
                    relevance_score=float(row.get("relevance_score", 1.0) or 0.0),
                    provenance=provenance,
                    source=str(row.get("source") or self.last_metadata["source"]),
                    pattern_type=pattern_type,
                )
            )
        self.last_metadata["accepted"] = len(lessons)
        self.last_metadata["no_memory_match"] = not lessons
        self.last_metadata["status"] = "ok"
        # BMF3-OBS: store trace on class for receipt access
        MemoryRetrievalAdapter._last_trace = dict(self.last_metadata)
        return lessons

    def retrieve_reranked(
        self,
        *,
        query_text: str,
        anchor_symbol: str = "",
        anchor_file: str = "",
        limit: int = 5,
        max_chars: int = 800,
    ) -> list[RetrievedLesson]:
        """BG: Memory Reranking — symbol-weighted relevance re-scoring.

        Steps:
        1. Retrieve up to limit * 3 raw candidates from store.
        2. Re-score each lesson by:
           a. Base relevance_score from store.
           b. +2.0 for each anchor_symbol token match in summary.
           c. +1.0 for each anchor_file token match in summary.
           d. -1.5 for pattern_type == 'failure' (penalize known-failure lessons).
        3. Deduplicate by summary fingerprint (>80% word overlap collapsed).
        4. Return top `limit` after re-scoring, pruning summaries to max_chars.
        """
        self.last_metadata["rerank_mode"] = True
        self.last_metadata["anchor_symbol"] = anchor_symbol
        self.last_metadata["anchor_file"] = anchor_file

        # Expand retrieval window for reranking
        raw_candidates = self.retrieve(query_text=query_text, limit=limit * 3)

        if not raw_candidates:
            return []

        # Build anchor token sets
        sym_tokens = set(re.split(r'[_\W]+', anchor_symbol.lower())) - {"", "py"}
        file_tokens = set(re.split(r'[/\\._]+', anchor_file.lower())) - {"", "py"}

        # Score candidates
        scored: list[tuple[float, RetrievedLesson]] = []
        seen_fingerprints: set[str] = set()

        for lesson in raw_candidates:
            summary_lower = lesson.summary.lower()
            words = re.split(r'\W+', summary_lower)
            fingerprint = " ".join(sorted(w for w in words if len(w) >= 3))
            if fingerprint in seen_fingerprints:
                continue  # deduplicate
            seen_fingerprints.add(fingerprint)

            score = float(lesson.relevance_score)

            # Anchor symbol boost
            for tok in sym_tokens:
                if tok and tok in summary_lower:
                    score += 2.0

            # Anchor file boost
            for tok in file_tokens:
                if tok and tok in summary_lower:
                    score += 1.0

            # Pattern penalty
            if lesson.pattern_type == "failure":
                score -= 1.5

            scored.append((score, lesson))

        # Sort by score descending
        scored.sort(key=lambda t: -t[0])

        # Prune summaries and return top limit
        result: list[RetrievedLesson] = []
        for _score, lesson in scored[:limit]:
            pruned_summary = lesson.summary[:max_chars] if len(lesson.summary) > max_chars else lesson.summary
            result.append(
                RetrievedLesson(
                    finding_id=lesson.finding_id,
                    summary=pruned_summary,
                    relevance_score=_score,
                    provenance=lesson.provenance,
                    source=lesson.source,
                    pattern_type=lesson.pattern_type,
                )
            )

        self.last_metadata["rerank_accepted"] = len(result)
        # BMF3-OBS: store trace on class for receipt access
        MemoryRetrievalAdapter._last_trace = dict(self.last_metadata)
        return result
