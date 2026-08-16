"""Formal ctx-scoped memory trace contract for local_heal.

Carries explicit retrieval, provenance, receipt, and presentation lineage without
adding routing, verifier, approval, or replay authority.
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
    retrieval_sources: list[str] = field(default_factory=list)
    query_text_hash: str = ""
    retrieved_count: int = 0
    selected_ids: list[str] = field(default_factory=list)
    memory_evidence_ids: list[str] = field(default_factory=list)
    provenance_count: int = 0
    rerank_mode: bool | None = None
    anchor_symbol: str | None = None
    anchor_file: str | None = None
    no_memory_match: bool | None = None
    rejected_without_provenance: int = 0
    evidence_packet_included: bool | None = None
    prompt_included: bool | None = None
    verifier_status: str = "NOT_MEASURED"
    learning_closure_id: str = ""
    findings_card_id: str = ""
    influence_status: str = "NOT_MEASURED"
    source_contract: str = "MEMORY_RETRIEVAL_ADAPTER"
    internal_only: bool = True
    # BMF10-RSH: shadow ranking telemetry
    shadow_ranking: dict[str, Any] = field(default_factory=dict)
    primary_selected_id: str = ""
    retrieval_receipt: dict[str, Any] = field(default_factory=dict)
    retrieval_receipt_hash: str = ""
    selected_lesson_lineage: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "trace_status": self.trace_status,
            "retrieval_source": self.retrieval_source,
            "retrieval_sources": list(self.retrieval_sources),
            "query_text_hash": self.query_text_hash,
            "retrieved_count": self.retrieved_count,
            "selected_ids": list(self.selected_ids),
            "memory_evidence_ids": list(self.memory_evidence_ids),
            "provenance_count": self.provenance_count,
            "rerank_mode": self.rerank_mode,
            "anchor_symbol": self.anchor_symbol,
            "anchor_file": self.anchor_file,
            "no_memory_match": self.no_memory_match,
            "rejected_without_provenance": self.rejected_without_provenance,
            "evidence_packet_included": self.evidence_packet_included,
            "prompt_included": self.prompt_included,
            "verifier_status": self.verifier_status,
            "learning_closure_id": self.learning_closure_id,
            "findings_card_id": self.findings_card_id,
            "influence_status": self.influence_status,
            "source_contract": self.source_contract,
            "internal_only": self.internal_only,
            "shadow_ranking": dict(self.shadow_ranking),
            "primary_selected_id": self.primary_selected_id,
            "retrieval_receipt": dict(self.retrieval_receipt),
            "retrieval_receipt_hash": self.retrieval_receipt_hash,
            "selected_lesson_lineage": [dict(item) for item in self.selected_lesson_lineage],
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

    query_hash = str(adapter_metadata.get("query_text_hash") or "")
    if not query_hash and query_text:
        query_hash = hashlib.sha256(query_text.encode()).hexdigest()[:16]

    retrieved = int(adapter_metadata.get("accepted", 0))
    rejected = int(adapter_metadata.get("rejected_without_provenance", 0))
    sources = list(adapter_metadata.get("retrieval_sources") or [])
    source = str(adapter_metadata.get("source", "") or (sources[0] if sources else ""))
    ids = list(selected_ids or adapter_metadata.get("selected_ids") or [])
    evidence_ids = list(adapter_metadata.get("memory_evidence_ids") or ids)

    return MemoryTrace(
        available=True,
        trace_status="TRACE_AVAILABLE" if retrieved > 0 else "TRACE_MISSING",
        retrieval_source=source,
        retrieval_sources=sources or ([source] if source else []),
        query_text_hash=query_hash,
        retrieved_count=retrieved,
        selected_ids=ids,
        memory_evidence_ids=evidence_ids,
        provenance_count=retrieved,
        rerank_mode=adapter_metadata.get("rerank_mode"),
        anchor_symbol=adapter_metadata.get("anchor_symbol"),
        anchor_file=adapter_metadata.get("anchor_file"),
        no_memory_match=adapter_metadata.get("no_memory_match"),
        rejected_without_provenance=rejected,
        evidence_packet_included=adapter_metadata.get("evidence_packet_included"),
        prompt_included=adapter_metadata.get("prompt_included"),
        verifier_status=str(adapter_metadata.get("verifier_status") or "NOT_MEASURED"),
        learning_closure_id=str(adapter_metadata.get("learning_closure_id") or ""),
        findings_card_id=str(adapter_metadata.get("findings_card_id") or ""),
        influence_status="NOT_MEASURED",
        source_contract="MEMORY_RETRIEVAL_ADAPTER",
        shadow_ranking=dict(adapter_metadata.get("shadow_ranking") or {}),
        primary_selected_id=str(adapter_metadata.get("primary_selected_id") or (ids[0] if ids else "")),
        retrieval_receipt=dict(adapter_metadata.get("retrieval_receipt") or {}),
        retrieval_receipt_hash=str(adapter_metadata.get("retrieval_receipt_hash") or ""),
        selected_lesson_lineage=[
            dict(item)
            for item in (adapter_metadata.get("selected_lesson_lineage") or [])
            if isinstance(item, dict)
        ],
    )


def get_empty_trace() -> MemoryTrace:
    """Return empty trace for cases where no memory retrieval occurred."""
    return MemoryTrace(
        available=False,
        trace_status="TRACE_MISSING",
        influence_status="NOT_MEASURED",
    )
