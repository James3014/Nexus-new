from __future__ import annotations

import hashlib
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
    task_id: str = ""

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


class FindingsMemoryLessonStore:
    """Read local-heal lessons from the existing structured FindingsMemoryStore."""

    def __init__(self, project_root: Path | None = None, findings_store: Any | None = None) -> None:
        self.project_root = project_root or Path(__file__).resolve().parents[3]
        self.findings_store = findings_store
        self.last_error: str = ""

    def _store(self) -> Any:
        if self.findings_store is not None:
            return self.findings_store
        from nexus.research.findings_memory import FindingsMemoryStore

        self.findings_store = FindingsMemoryStore(self.project_root)
        return self.findings_store

    def query(self, *, query_text: str, limit: int) -> list[dict[str, Any]]:
        self.last_error = ""
        try:
            store = self._store()
            cards = list(store.search(query_text, kind="episodes", scope="both"))
            if not cards:
                tokens = [token for token in re.split(r"[_\W]+", query_text.lower()) if len(token) >= 3]
                seen_ids: set[str] = set()
                for token in tokens[:8]:
                    for card in store.search(token, kind="episodes", scope="both"):
                        card_id = str(getattr(card, "id", ""))
                        if card_id in seen_ids:
                            continue
                        seen_ids.add(card_id)
                        cards.append(card)
                        if len(cards) >= limit:
                            break
                    if len(cards) >= limit:
                        break
        except Exception as exc:
            self.last_error = exc.__class__.__name__
            return []

        rows: list[dict[str, Any]] = []
        for card in cards[:limit]:
            extra = dict(getattr(card, "extra", {}) or {})
            evidence_paths = list(getattr(card, "evidence_paths", []) or [])
            rows.append(
                {
                    "lesson_id": extra.get("lesson_id") or getattr(card, "id", ""),
                    "finding_id": getattr(card, "id", ""),
                    "task_id": getattr(card, "task_id", "") or extra.get("task_id", ""),
                    "classification": extra.get("classification") or ",".join(getattr(card, "tags", []) or []),
                    "summary": getattr(card, "body", "") or getattr(card, "title", ""),
                    "provenance": evidence_paths[0] if evidence_paths else extra.get("receipt_id", ""),
                    "relevance_score": 1.0,
                    "source": "FindingsMemoryStore",
                }
            )
        return rows


class MemoryRepositoryLessonStore:
    """Optional LanceDB/MemoryRepository read path for findings_cards."""

    def __init__(self, project_root: Path | None = None, repository: Any | None = None) -> None:
        self.project_root = project_root or Path(__file__).resolve().parents[3]
        self.repository = repository
        self.last_error: str = ""

    def _repository(self) -> Any:
        if self.repository is not None:
            return self.repository
        from nexus.services.memory_repository import MemoryRepository

        self.repository = MemoryRepository(self.project_root / ".nexus" / "memory_repository")
        return self.repository

    def query(self, *, query_text: str, limit: int) -> list[dict[str, Any]]:
        self.last_error = ""
        try:
            frame = self._repository().search_fts(
                "findings_cards",
                query_text,
                limit=limit,
                fallback_columns=["title", "body", "content", "aaak_content"],
            )
        except Exception as exc:
            self.last_error = exc.__class__.__name__
            return []
        if getattr(frame, "empty", True):
            return []
        return [dict(row) for row in frame.head(limit).to_dict(orient="records")]


class NexusCompositeLessonStore:
    """Composite Nexus memory read path with bounded, fail-open sources."""

    def __init__(self, stores: list[LessonStore] | None = None) -> None:
        self.stores = stores or [
            LocalJsonlLessonStore(),
            FindingsMemoryLessonStore(),
            MemoryRepositoryLessonStore(),
        ]
        self.last_metadata: dict[str, Any] = {}

    def query(self, *, query_text: str, limit: int) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        sources: list[str] = []
        source_counts: dict[str, int] = {}
        source_errors: dict[str, str] = {}

        for store in self.stores:
            source = store.__class__.__name__
            try:
                store_rows = list(store.query(query_text=query_text, limit=limit))
            except Exception as exc:
                store_rows = []
                source_errors[source] = exc.__class__.__name__
            last_error = str(getattr(store, "last_error", "") or "")
            if last_error:
                source_errors[source] = last_error
            if store_rows:
                sources.append(source)
                source_counts[source] = len(store_rows)
            rows.extend(store_rows)

        self.last_metadata = {
            "retrieval_sources": sources,
            "source_counts": source_counts,
            "source_errors": source_errors,
        }
        return rows[:limit]


class MemoryRetrievalAdapter:
    """Retrieves provenance-backed local-heal lessons.

    LanceDB can be supplied as a store with the same query contract. The default
    local JSONL fallback is intentionally bounded and fail-open: no store or no
    match records no_memory_match instead of blocking repair.
    """

    def __init__(self, store: LessonStore | None = None, *, enabled: bool = True, memory_arm: str = "") -> None:
        self.store = store or NexusCompositeLessonStore()
        self.enabled = enabled
        self.memory_arm = memory_arm
        self.last_metadata: dict[str, Any] = {}

    def retrieve(self, *, query_text: str, limit: int = 5) -> list[RetrievedLesson]:
        self.last_metadata = {
            "enabled": bool(self.enabled),
            "query_text_hash": hashlib.sha256(query_text.encode()).hexdigest()[:16] if query_text else "",
            "no_memory_match": False,
            "rejected_without_provenance": 0,
            "source": self.store.__class__.__name__,
            "retrieval_sources": [],
            "source_errors": {},
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
        seen: set[tuple[str, str]] = set()
        for row in raw_rows:
            provenance = str(row.get("provenance") or row.get("receipt_id") or row.get("evidence_ref") or "").strip()
            if not provenance:
                self.last_metadata["rejected_without_provenance"] += 1
                continue
            finding_id = str(row.get("lesson_id") or row.get("finding_id") or row.get("id") or row.get("task_id") or "lesson")
            summary = str(row.get("summary") or row.get("lesson") or row.get("body") or row.get("content") or "")
            fingerprint = (finding_id, provenance)
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            classification = str(row.get("classification") or row.get("pattern_type") or "").lower()
            pattern_type = "failure" if any(token in classification for token in ("fail", "unsupported", "gap", "owner")) else "success"
            lessons.append(
                RetrievedLesson(
                    finding_id=finding_id,
                    summary=summary,
                    relevance_score=float(row.get("relevance_score", 1.0) or 0.0),
                    provenance=provenance,
                    source=str(row.get("source") or self.last_metadata["source"]),
                    pattern_type=pattern_type,
                    task_id=str(row.get("task_id") or ""),
                )
            )

        self.last_metadata["accepted"] = len(lessons)
        self.last_metadata["no_memory_match"] = not lessons
        self.last_metadata["status"] = "ok"
        self.last_metadata["selected_ids"] = [lesson.finding_id for lesson in lessons]
        self.last_metadata["memory_evidence_ids"] = [lesson.finding_id for lesson in lessons]
        self.last_metadata["primary_selected_id"] = lessons[0].finding_id if lessons else ""
        store_metadata = dict(getattr(self.store, "last_metadata", {}) or {})
        if store_metadata:
            self.last_metadata["retrieval_sources"] = list(store_metadata.get("retrieval_sources") or [])
            self.last_metadata["source_errors"] = dict(store_metadata.get("source_errors") or {})
            self.last_metadata["source_counts"] = dict(store_metadata.get("source_counts") or {})
        return lessons

    def retrieve_reranked(
        self,
        *,
        query_text: str,
        anchor_symbol: str = "",
        anchor_file: str = "",
        limit: int = 5,
        max_chars: int = 800,
        task_id: str = "",
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
        # Expand retrieval window for reranking
        raw_candidates = self.retrieve(query_text=query_text, limit=limit * 3)
        self.last_metadata["rerank_mode"] = True
        self.last_metadata["anchor_symbol"] = anchor_symbol
        self.last_metadata["anchor_file"] = anchor_file

        if not raw_candidates:
            # BMF10-RSH: shadow metadata for empty case
            self.last_metadata["shadow_ranking"] = {
                "enabled": True,
                "status": "NO_LESSONS",
                "scored_count": 0,
                "rank_changes": 0,
                "top_current_ids": [],
                "top_proposed_ids": [],
                "feature_coverage": 0.0,
                "runtime_order_changed": False,
                "prompt_changed": False,
                "verifier_changed": False,
                "shadow_only": True,
            }
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

            # Task ID match boost
            if task_id and lesson.task_id:
                def normalize_id(t: str) -> str:
                    return re.sub(r'[^a-zA-Z0-9]', '', t).lower()
                if normalize_id(lesson.task_id) == normalize_id(task_id):
                    score += 10.0

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
                    task_id=lesson.task_id,
                )
            )

        self.last_metadata["rerank_accepted"] = len(result)
        self.last_metadata["selected_ids"] = [lesson.finding_id for lesson in result]
        self.last_metadata["memory_evidence_ids"] = [lesson.finding_id for lesson in result]
        self.last_metadata["primary_selected_id"] = result[0].finding_id if result else ""

        # BMF10-RSH: shadow ranking telemetry (runtime order UNCHANGED)
        try:
            from nexus.services.local_heal.shadow_memory_ranking import shadow_score_lessons
            lesson_dicts = [
                {"lesson_id": l.finding_id, "summary": l.summary, "classification": l.pattern_type,
                 "provenance": l.provenance, "source": l.source, "relevance_score": l.relevance_score}
                for l in raw_candidates
            ]
            shadow = shadow_score_lessons(
                lesson_dicts,
                anchor_symbol=anchor_symbol,
                anchor_file=anchor_file,
                limit=limit,
            )
            self.last_metadata["shadow_ranking"] = {
                "enabled": True,
                "status": "COMPLETED",
                "scored_count": shadow.shadow_scored_count,
                "rank_changes": shadow.shadow_rank_changes,
                "top_current_ids": shadow.top_current_ids,
                "top_proposed_ids": shadow.top_proposed_ids,
                "feature_coverage": shadow.shadow_feature_coverage,
                "runtime_order_changed": False,
                "prompt_changed": False,
                "verifier_changed": False,
                "shadow_only": True,
            }
        except Exception as exc:
            self.last_metadata["shadow_ranking"] = {
                "enabled": True,
                "status": "FAILED_FAIL_OPEN",
                "error": exc.__class__.__name__,
                "runtime_order_changed": False,
                "prompt_changed": False,
                "verifier_changed": False,
                "shadow_only": True,
            }
        # Ensure shadow_ranking always present even if no lessons
        if "shadow_ranking" not in self.last_metadata:
            self.last_metadata["shadow_ranking"] = {
                "enabled": True,
                "status": "NO_LESSONS",
                "scored_count": 0,
                "rank_changes": 0,
                "top_current_ids": [],
                "top_proposed_ids": [],
                "feature_coverage": 0.0,
                "runtime_order_changed": False,
                "prompt_changed": False,
                "verifier_changed": False,
                "shadow_only": True,
            }

        return result
