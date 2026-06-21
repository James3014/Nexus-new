"""BMF3-OBS: Formal ctx-scoped memory trace contract for local_heal.

Replaces module-level _last_memory_trace global with explicit data flow.
No behavior change to retrieval, ranking, or prompt.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MemoryTrace:
    """Ctx-scoped memory trace for receipt and learning closure.
    
    Contract:
    - available: whether memory retrieval was attempted
    - trace_status: TRACE_AVAILABLE | TRACE_MISSING | NOT_USED
    - selected_ids: list of lesson finding_ids that were selected
    - provenance_count: count of lessons with valid provenance
    - influence_status: NOT_MEASURED | UNKNOWN (never infer helped/harmed)
    """
    available: bool = False
    trace_status: str = "NOT_USED"
    retrieval_source: str = ""
    query_text_hash: str = ""
    retrieved_count: int = 0
    selected_ids: list[str] = field(default_factory=list)
    provenance_count: int = 0
    rerank_mode: bool | None = None
    anchor_symbol: str | None = None
    anchor_file: str | None = None
    no_memory_match: bool | None = None
    rejected_without_provenance: int = 0
    influence_status: str = "NOT_MEASURED"
    source_contract: str = "MEMORY_RETRIEVAL_ADAPTER"
    internal_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "trace_status": self.trace_status,
            "retrieval_source": self.retrieval_source,
            "query_text_hash": self.query_text_hash,
            "retrieved_count": self.retrieved_count,
            "selected_ids": list(self.selected_ids),
            "provenance_count": self.provenance_count,
            "rerank_mode": self.rerank_mode,
            "anchor_symbol": self.anchor_symbol,
            "anchor_file": self.anchor_file,
            "no_memory_match": self.no_memory_match,
            "rejected_without_provenance": self.rejected_without_provenance,
            "influence_status": self.influence_status,
            "source_contract": self.source_contract,
            "internal_only": self.internal_only,
        }


def build_memory_trace_from_adapter(
    adapter_metadata: dict[str, Any],
    *,
    selected_ids: list[str] | None = None,
    query_text: str = "",
) -> MemoryTrace:
    """Build MemoryTrace from MemoryRetrievalAdapter.last_metadata.
    
    This is the single conversion point from adapter output to ctx-scoped trace.
    No other module should read adapter metadata directly.
    """
    if not adapter_metadata:
        return MemoryTrace()

    query_hash = hashlib.sha256(query_text.encode()).hexdigest()[:16] if query_text else ""

    retrieved = int(adapter_metadata.get("accepted", 0))
    rejected = int(adapter_metadata.get("rejected_without_provenance", 0))

    return MemoryTrace(
        available=True,
        trace_status="TRACE_AVAILABLE" if retrieved > 0 else "TRACE_MISSING",
        retrieval_source=adapter_metadata.get("source", ""),
        query_text_hash=query_hash,
        retrieved_count=retrieved,
        selected_ids=list(selected_ids or []),
        provenance_count=retrieved - rejected,
        rerank_mode=adapter_metadata.get("rerank_mode"),
        anchor_symbol=adapter_metadata.get("anchor_symbol"),
        anchor_file=adapter_metadata.get("anchor_file"),
        no_memory_match=adapter_metadata.get("no_memory_match"),
        rejected_without_provenance=rejected,
        influence_status="NOT_MEASURED",
        source_contract="MEMORY_RETRIEVAL_ADAPTER",
    )


def get_empty_trace() -> MemoryTrace:
    """Return empty trace for cases where no memory retrieval occurred."""
    return MemoryTrace(
        available=False,
        trace_status="TRACE_MISSING",
        influence_status="NOT_MEASURED",
    )
