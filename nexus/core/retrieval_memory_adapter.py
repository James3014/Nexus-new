from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class MemoryStore(Protocol):
    def build_write_guard_receipt(self, *, concurrent_writer_count: int = 1) -> dict[str, Any]: ...

    def add_insight_guarded(
        self,
        topic: str,
        content: str,
        insight_type: str = "RCA",
        *,
        concurrent_writer_count: int = 1,
    ) -> dict[str, Any]: ...

    def search(self, query: str): ...


@dataclass(frozen=True)
class RetrievalMemoryAdapter:
    """Read/write adapter for retrieval memory with explicit claim boundaries."""

    store: MemoryStore

    def write(
        self,
        *,
        topic: str,
        content: str,
        insight_type: str = "RCA",
        concurrent_writer_count: int = 1,
    ) -> dict[str, Any]:
        result = self.store.add_insight_guarded(
            topic,
            content,
            insight_type,
            concurrent_writer_count=concurrent_writer_count,
        )
        return {
            "schema": "nexus.retrieval_memory_write.v1",
            "status": str(result.get("status") or "RETURN"),
            "written": bool(result.get("written", False)),
            "topic": topic,
            "write_result": result,
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
            "blockers": list(result.get("blockers", []) or []),
            "claim_boundary": [
                "Retrieval memory writes confirm guarded local persistence only.",
                "They do not imply retrieval relevance, learning closure success, or public readiness.",
            ],
        }

    def read(self, *, query: str, limit: int = 10) -> dict[str, Any]:
        rows = list(self.store.search(query))[: max(0, int(limit))]
        return {
            "schema": "nexus.retrieval_memory_read.v1",
            "status": "PASS",
            "query": query,
            "result_count": len(rows),
            "results": [_row_to_dict(row) for row in rows],
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
            "blockers": [],
            "claim_boundary": [
                "Retrieval memory reads expose local candidate context only.",
                "They do not decide route quality, claim truth, or public benchmark readiness.",
            ],
        }


def _row_to_dict(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return dict(row)
    if isinstance(row, (list, tuple)):
        keys = ("topic", "content", "type", "timestamp")
        return {key: row[index] for index, key in enumerate(keys) if index < len(row)}
    return {"value": str(row)}
