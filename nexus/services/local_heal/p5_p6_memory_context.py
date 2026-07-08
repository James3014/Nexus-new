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
        from nexus.services.local_heal.memory_retrieval_adapter import MemoryRetrievalAdapter
        from nexus.services.local_heal.memory_trace import get_empty_trace

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

        # Convert lessons to dicts
        lesson_dicts = []
        for lesson in lessons:
            if hasattr(lesson, "summary"):
                lesson_dicts.append({"summary": lesson.summary, "source": getattr(lesson, "source", "unknown")})
            elif hasattr(lesson, "content"):
                lesson_dicts.append({"content": lesson.content, "source": getattr(lesson, "source", "unknown")})
            else:
                lesson_dicts.append({"content": str(lesson), "source": "unknown"})

        sources = list(set(d.get("source", "unknown") for d in lesson_dicts))

        return P5P6MemoryContext(
            memory_trace=get_empty_trace().to_dict(),
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
