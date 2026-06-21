from __future__ import annotations

import json
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
        return lessons
