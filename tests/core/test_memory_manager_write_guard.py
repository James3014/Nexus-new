from __future__ import annotations

from pathlib import Path

from nexus.core.memory_manager import ProjectMemoryManager


def test_project_memory_manager_write_guard_uses_wal(tmp_path: Path) -> None:
    manager = ProjectMemoryManager(tmp_path)

    payload = manager.build_write_guard_receipt()

    assert payload["status"] == "PASS"
    assert payload["wal_status"] == "PASS"
    assert payload["target_path"].endswith("project_memory.sqlite")


def test_project_memory_manager_write_guard_blocks_unqueued_concurrency(tmp_path: Path) -> None:
    manager = ProjectMemoryManager(tmp_path)

    payload = manager.build_write_guard_receipt(concurrent_writer_count=4)

    assert payload["status"] == "RETURN"
    assert "write_queue_not_pass" in payload["blockers"]
    assert "backoff_not_pass" in payload["blockers"]
