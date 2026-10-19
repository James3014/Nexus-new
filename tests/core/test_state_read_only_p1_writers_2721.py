"""#2721 L-B: P1-reachable learning-state writers honour NEXUS_STATE_READ_ONLY=1.

Covers ProjectMemoryManager (sqlite), StateJsonStore/_FileLock, and MemoryRepository
(lancedb). The switch is read at call time, never cached at construction.
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest

from nexus.core.memory_manager import ProjectMemoryManager
from nexus.infrastructure.state_json_store import StateJsonStore
from nexus.services.memory_repository import MemoryRepository

RO = "NEXUS_STATE_READ_ONLY"


def tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if path.is_dir():
            digest.update(f"D:{rel}\n".encode())
        else:
            digest.update(f"F:{rel}:".encode())
            digest.update(path.read_bytes())
            digest.update(b"\n")
    return digest.hexdigest()


def names(root: Path) -> list[str]:
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*"))


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv(RO, raising=False)
    monkeypatch.delenv("NEXUS_STATE_ROOT", raising=False)


# ---- 1. ProjectMemoryManager ---------------------------------------------------------


def test_memory_manager_fresh_root_creates_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv(RO, "1")
    mgr = ProjectMemoryManager(tmp_path)
    assert mgr.search("x") == []
    mgr.add_insight("t", "c")
    result = mgr.add_insight_guarded("t", "c")
    assert result["written"] is False and result["blockers"] == ["state_read_only"]
    mgr.init_db()
    assert names(tmp_path) == []


def test_memory_manager_existing_store_reads_without_wal(tmp_path, monkeypatch):
    mgr = ProjectMemoryManager(tmp_path)
    mgr.add_insight("topic", "hello world")
    # Fold the WAL into the main file so the tree is stable, then drop side files.
    with sqlite3.connect(mgr.db_path) as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    for suffix in ("-wal", "-shm"):
        Path(str(mgr.db_path) + suffix).unlink(missing_ok=True)
    before = tree_hash(tmp_path)

    monkeypatch.setenv(RO, "1")
    ro = ProjectMemoryManager(tmp_path)
    assert [row[1] for row in ro.search("hello")] == ["hello world"]
    ro.add_insight("topic", "must not land")
    ro.add_insight_guarded("topic", "must not land")
    assert tree_hash(tmp_path) == before
    assert not list(tmp_path.rglob("*-wal")) and not list(tmp_path.rglob("*-shm"))

    monkeypatch.delenv(RO)
    assert [row[1] for row in ProjectMemoryManager(tmp_path).search("")] == ["hello world"]


def test_memory_manager_switch_not_cached_at_construction(tmp_path, monkeypatch):
    mgr = ProjectMemoryManager(tmp_path)  # constructed with switch unset
    monkeypatch.setenv(RO, "1")
    mgr.add_insight("t", "late")
    assert mgr.search("late") == []
    monkeypatch.delenv(RO)
    assert mgr.search("late") == []  # the write above was skipped


def test_memory_manager_unset_creates_and_writes(tmp_path):
    mgr = ProjectMemoryManager(tmp_path)
    assert mgr.db_path.exists()
    mgr.add_insight("t", "kept")
    assert [row[1] for row in mgr.search("kept")] == ["kept"]


# ---- 2. StateJsonStore -----------------------------------------------------------------


def test_json_store_fresh_root_creates_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv(RO, "1")
    store = StateJsonStore()
    path = tmp_path / "state" / "belief.json"
    assert store.read_dict(path) == {}
    store.write_dict(path, {"a": 1})
    assert store.merge_dict(path, {"a": 1}) == {}
    assert store.compare_and_swap_dict(path, None, {"a": 1}) is False
    assert names(tmp_path) == []


def test_json_store_existing_reads_without_lock(tmp_path, monkeypatch):
    store = StateJsonStore()
    path = tmp_path / "belief.json"
    store.write_dict(path, {"a": 1})
    path.with_suffix(".json.lock").unlink()
    before = tree_hash(tmp_path)

    monkeypatch.setenv(RO, "1")
    assert store.read_dict(path) == {"a": 1}
    store.write_dict(path, {"a": 2})
    assert store.merge_dict(path, {"b": 2}) == {"a": 1}
    assert store.compare_and_swap_dict(path, store.content_digest({"a": 1}), {"a": 3}) is False
    assert tree_hash(tmp_path) == before
    assert not list(tmp_path.rglob("*.lock"))


def test_json_store_existing_lock_file_is_reused_not_changed(tmp_path, monkeypatch):
    store = StateJsonStore()
    path = tmp_path / "belief.json"
    store.write_dict(path, {"a": 1})
    before = tree_hash(tmp_path)
    monkeypatch.setenv(RO, "1")
    assert store.read_dict(path) == {"a": 1}
    assert tree_hash(tmp_path) == before


def test_json_store_unset_still_writes_with_lock(tmp_path):
    store = StateJsonStore()
    path = tmp_path / "sub" / "x.json"
    store.write_dict(path, {"a": 1})
    assert store.read_dict(path) == {"a": 1}
    assert store.merge_dict(path, {"b": 2}) == {"a": 1, "b": 2}
    assert (tmp_path / "sub" / "x.json.lock").exists()


def test_belief_engine_reads_under_switch(tmp_path, monkeypatch):
    from nexus.core.belief_engine import BeliefEngine

    state = tmp_path / "belief.json"
    StateJsonStore().write_dict(state, {"seed": {"x": 1}})
    state.with_suffix(".json.lock").unlink()
    before = tree_hash(tmp_path)
    monkeypatch.setenv(RO, "1")
    engine = BeliefEngine(state_file=state)
    assert isinstance(engine, BeliefEngine)
    assert tree_hash(tmp_path) == before


# ---- 3. MemoryRepository (lancedb) -------------------------------------------------------


def test_repository_fresh_root_creates_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv(RO, "1")
    repo = MemoryRepository(tmp_path / ".nexus" / "knowledge" / "lancedb")
    assert repo.list_tables() == []
    assert repo.get_all_rows("policy").empty
    assert repo.search_fts("policy", "q").empty
    repo.add_rows("policy", [{"id": "1", "content": "c"}])
    repo.ensure_table("policy", initial_data=[{"id": "1", "content": "c"}])
    repo.update_table("policy", [{"id": "1", "content": "c"}])
    assert repo.semantic_dedup_ingest("policy", {"id": "1", "content": "c"}) == "SKIPPED_READ_ONLY"
    assert names(tmp_path) == []


def test_repository_existing_store_reads_and_is_unchanged(tmp_path, monkeypatch):
    pytest.importorskip("lancedb")
    root = tmp_path / "lancedb"
    writer = MemoryRepository(root)
    writer.add_rows("policy", [{"id": "1", "content": "alpha beta"}])
    writer._db = None
    before = tree_hash(tmp_path)

    monkeypatch.setenv(RO, "1")
    repo = MemoryRepository(root)
    assert repo.list_tables() == ["policy"]
    frame = repo.search_fts("policy", "alpha", fallback_columns=["content"])
    assert len(frame) == 1
    assert len(repo.get_all_rows("policy")) == 1
    repo.add_rows("policy", [{"id": "2", "content": "gamma"}])
    repo.update_table("policy", [{"id": "3", "content": "delta"}])
    assert tree_hash(tmp_path) == before


def test_repository_unset_creates_store(tmp_path):
    pytest.importorskip("lancedb")
    root = tmp_path / "nested" / "lancedb"
    repo = MemoryRepository(root)
    repo.add_rows("policy", [{"id": "1", "content": "c"}])
    assert root.exists() and repo.list_tables() == ["policy"]
