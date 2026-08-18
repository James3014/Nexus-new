from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class P5P6MemoryContext:
    """P5/P6 memory context adapter wrapping existing MemoryRetrievalAdapter."""
    memory_trace: dict[str, Any] = field(default_factory=dict)
    retrieved_lessons: list[dict[str, Any]] = field(default_factory=list)
    memory_sources: list[str] = field(default_factory=list)
    decision_mode: str = "audit_only"  # "audit_only" | "decision_eligible"
    decision_eligible: bool = False
    reason: str = ""


def build_p5_p6_memory_context(
    *,
    adapter_enabled: bool = False,
    query_text: str = "",
    anchor_symbol: str = "",
    anchor_file: str = "",
    task_id: str = "",
) -> P5P6MemoryContext:
    """Build P5/P6 memory context using existing MemoryRetrievalAdapter.

    Does NOT create parallel retrieval — consumes existing adapter.
    """
    if not adapter_enabled:
        return P5P6MemoryContext(
            memory_trace={},
            retrieved_lessons=[],
            memory_sources=[],
            decision_mode="audit_only",
            decision_eligible=False,
            reason="adapter_disabled",
        )

    try:
        from nexus.services.local_heal.memory_retrieval_adapter import (
            MemoryRetrievalAdapter,
            validate_retrieved_lesson_context_binding,
        )
        from nexus.services.local_heal.memory_trace import (
            build_memory_trace_from_adapter,
            get_empty_trace,
        )

        adapter = MemoryRetrievalAdapter(enabled=True)
        lessons = adapter.retrieve_reranked(
            query_text=query_text,
            anchor_symbol=anchor_symbol,
            anchor_file=anchor_file,
            limit=3,
            max_chars=800,
            task_id=task_id,
        )

        if not lessons:
            return P5P6MemoryContext(
                memory_trace=get_empty_trace().to_dict(),
                retrieved_lessons=[],
                memory_sources=[],
                decision_mode="audit_only",
                decision_eligible=False,
                reason="no_hits",
            )

        retrieval_receipt = dict(adapter.last_metadata.get("retrieval_receipt") or {})
        retrieval_receipt_hash = str(adapter.last_metadata.get("retrieval_receipt_hash") or "")
        if not validate_retrieved_lesson_context_binding(
            lessons,
            retrieval_receipt,
            retrieval_receipt_hash,
            query_text=query_text,
        ):
            return P5P6MemoryContext(
                memory_trace=build_memory_trace_from_adapter(
                    adapter.last_metadata,
                    query_text=query_text,
                ).to_dict(),
                retrieved_lessons=[],
                memory_sources=[],
                decision_mode="audit_only",
                decision_eligible=False,
                reason="binding_failed",
            )

        # Preserve provenance-bearing lineage instead of projecting to summary-only text.
        lesson_dicts = []
        for lesson in lessons:
            content = getattr(lesson, "summary", None) or getattr(lesson, "content", None) or str(lesson)
            lesson_dicts.append(
                {
                    "summary": str(content),
                    "source": getattr(lesson, "source", "unknown"),
                    "lesson_id": getattr(lesson, "finding_id", ""),
                    "episode_id": getattr(lesson, "episode_id", ""),
                    "task_id": getattr(lesson, "task_id", ""),
                    "attempt_id": getattr(lesson, "attempt_id", ""),
                    "action_id": getattr(lesson, "action_id", ""),
                    "qualification_status": getattr(lesson, "qualification_status", ""),
                    "validity_state": getattr(lesson, "validity_state", ""),
                    "evidence_ref": getattr(lesson, "evidence_ref", "")
                    or getattr(lesson, "provenance", ""),
                }
            )

        sources = list(set(d.get("source", "unknown") for d in lesson_dicts))

        return P5P6MemoryContext(
            memory_trace=build_memory_trace_from_adapter(
                adapter.last_metadata,
                query_text=query_text,
            ).to_dict(),
            retrieved_lessons=lesson_dicts,
            memory_sources=sources,
            decision_mode="audit_only",
            decision_eligible=False,  # audit-only until copyability proven
            reason="hits_available",
        )

    except ImportError:
        return P5P6MemoryContext(
            memory_trace={},
            retrieved_lessons=[],
            memory_sources=[],
            decision_mode="audit_only",
            decision_eligible=False,
            reason="adapter_import_failed",
        )
