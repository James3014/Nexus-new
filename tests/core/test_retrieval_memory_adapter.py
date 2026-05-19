from __future__ import annotations

from pathlib import Path

from nexus.core.memory_manager import ProjectMemoryManager
from nexus.core.retrieval_memory_adapter import RetrievalMemoryAdapter


def test_retrieval_memory_adapter_writes_and_reads_guarded_memory(tmp_path: Path) -> None:
    adapter = RetrievalMemoryAdapter(ProjectMemoryManager(tmp_path))

    write = adapter.write(topic="route", content="runtime plan consumed", insight_type="ARCH")
    read = adapter.read(query="runtime plan", limit=5)

    assert write["schema"] == "nexus.retrieval_memory_write.v1"
    assert write["status"] == "PASS"
    assert write["written"] is True
    assert write["runtime_update_allowed"] is False
    assert write["public_benchmark_allowed"] is False
    assert read["schema"] == "nexus.retrieval_memory_read.v1"
    assert read["status"] == "PASS"
    assert read["result_count"] == 1
    assert read["results"][0]["topic"] == "route"
    assert read["results"][0]["content"] == "runtime plan consumed"


def test_retrieval_memory_adapter_blocks_write_when_guard_returns(tmp_path: Path) -> None:
    adapter = RetrievalMemoryAdapter(ProjectMemoryManager(tmp_path))

    write = adapter.write(
        topic="route",
        content="should not persist",
        insight_type="ARCH",
        concurrent_writer_count=4,
    )
    read = adapter.read(query="should not persist")

    assert write["status"] == "RETURN"
    assert write["written"] is False
    assert "write_queue_not_pass" in write["blockers"]
    assert read["result_count"] == 0
