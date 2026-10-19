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


def _populated_with_live_wal(tmp_path: Path, *, keep_shm: bool):
    """A DB whose newest row lives only in a live -wal (writer connection left open)."""
    mgr = ProjectMemoryManager(tmp_path)
    mgr.add_insight("topic", "in main file")
    with sqlite3.connect(mgr.db_path) as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    writer = sqlite3.connect(mgr.db_path)
    writer.execute("PRAGMA journal_mode=WAL")
    writer.execute("PRAGMA wal_autocheckpoint=0")
    writer.execute(
        "INSERT INTO insights (topic, content, type) VALUES ('t', 'wal only row', 'RCA')"
    )
    writer.commit()
    wal = Path(str(mgr.db_path) + "-wal")
    shm = Path(str(mgr.db_path) + "-shm")
    assert wal.exists() and wal.stat().st_size > 0
    # Snapshot the files as a crashed/frozen writer would leave them, then close the writer.
    frozen = tmp_path.parent / (tmp_path.name + "-frozen")
    frozen.mkdir()
    for src in (mgr.db_path, wal, shm):
        if src.exists() and (keep_shm or src != shm):
            (frozen / src.name).write_bytes(src.read_bytes())
    writer.close()
    for src in (mgr.db_path, wal, shm):
        src.unlink(missing_ok=True)
    for src in frozen.iterdir():
        (mgr.db_path.parent / src.name).write_bytes(src.read_bytes())
    return mgr


@pytest.mark.parametrize("keep_shm", [False, True])
def test_memory_manager_live_wal_rows_visible_and_tree_unchanged(tmp_path, monkeypatch, keep_shm):
    mgr = _populated_with_live_wal(tmp_path, keep_shm=keep_shm)
    wal = Path(str(mgr.db_path) + "-wal")
    assert wal.exists()
    before = tree_hash(tmp_path)
    before_names = names(tmp_path)

    monkeypatch.setenv(RO, "1")
    ro = ProjectMemoryManager(tmp_path)
    found = sorted(row[1] for row in ro.search(""))
    assert found == ["in main file", "wal only row"]
    ro.add_insight("topic", "must not land")
    ro.add_insight_guarded("topic", "must not land")
    assert tree_hash(tmp_path) == before
    assert names(tmp_path) == before_names


def test_memory_manager_temp_copy_removed_on_close(tmp_path, monkeypatch):
    import glob
    import tempfile

    ProjectMemoryManager(tmp_path).add_insight("t", "x")
    monkeypatch.setenv(RO, "1")
    ro = ProjectMemoryManager(tmp_path)
    tree_before = tree_hash(tmp_path)
    pattern = str(Path(tempfile.gettempdir()) / "nexus-ro-sqlite-*")
    before = set(glob.glob(pattern))
    with ro._connect() as conn:
        assert conn.execute("select count(*) from insights").fetchone()[0] == 1
        assert len(set(glob.glob(pattern)) - before) == 1
    assert set(glob.glob(pattern)) == before
    assert tree_hash(tmp_path) == tree_before


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


def test_repository_ensure_new_table_on_populated_store_unchanged(tmp_path, monkeypatch):
    pytest.importorskip("lancedb")
    root = tmp_path / "lancedb"
    MemoryRepository(root).add_rows("policy", [{"id": "1", "content": "alpha"}])
    before = tree_hash(tmp_path)
    monkeypatch.setenv(RO, "1")
    repo = MemoryRepository(root)
    repo.ensure_table("brand_new", initial_data=[{"id": "9", "content": "z"}])
    assert repo.list_tables() == ["policy"]
    assert tree_hash(tmp_path) == before


def test_repository_built_before_switch_writes_nothing_after(tmp_path, monkeypatch):
    pytest.importorskip("lancedb")
    root = tmp_path / "lancedb"
    repo = MemoryRepository(root)
    repo.add_rows("policy", [{"id": "1", "content": "alpha"}])  # connects, caches _db
    before = tree_hash(tmp_path)
    monkeypatch.setenv(RO, "1")
    repo.add_rows("policy", [{"id": "2", "content": "beta"}])
    repo.add_rows("other", [{"id": "3", "content": "gamma"}])
    repo.update_table("policy", [{"id": "4", "content": "delta"}])
    assert repo.semantic_dedup_ingest("policy", {"id": "5", "content": "e"}) == "SKIPPED_READ_ONLY"
    assert tree_hash(tmp_path) == before
    monkeypatch.delenv(RO)
    repo.add_rows("policy", [{"id": "6", "content": "zeta"}])
    assert len(repo.get_all_rows("policy")) == 2


# ---- 4. MemoryService / MemoryCoordinator / findings sync ---------------------------------


def _lesson():
    from nexus.services.memory import FaultLesson

    return FaultLesson("h1", "E", "k", "lesson", "patch", 0.9)


def _service(root: Path):
    from nexus.services.memory import MemoryService

    return MemoryService(str(root), redis_client=_NoRedis())


class _NoRedis:
    def ping(self):
        return True

    def set(self, *a, **k):
        return True

    def get(self, *a, **k):
        return None


def test_memory_service_writers_noop_under_switch_fresh_root(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUS_MEMORY_AUTO_INIT", "0")
    svc = _service(tmp_path)
    monkeypatch.setenv(RO, "1")  # set AFTER construction: re-read per call
    result = svc.aggregate_memory("anything")
    assert set(result) >= {"reminders", "total_sources", "timestamp"}
    assert svc.record_fault_lesson(_lesson()) is None
    assert svc.sync_route_phase_weights({"P": 10.0}, "c", "h") is None
    assert names(tmp_path) == []


def test_memory_service_existing_store_unchanged_under_switch(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUS_MEMORY_AUTO_INIT", "0")
    svc = _service(tmp_path)
    svc.record_fault_lesson(_lesson())
    svc.sync_route_phase_weights({"P": 10.0}, "c", "h")
    svc.aggregate_memory("q")
    for lock in tmp_path.rglob("*.lock"):
        lock.unlink()
    before = tree_hash(tmp_path)
    monkeypatch.setenv(RO, "1")
    svc.record_fault_lesson(_lesson())
    svc.sync_route_phase_weights({"P": -50.0}, "c2", "h2")
    svc.aggregate_memory("q")
    assert tree_hash(tmp_path) == before


def test_memory_service_unset_still_writes(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUS_MEMORY_AUTO_INIT", "0")
    svc = _service(tmp_path)
    svc.aggregate_memory("q")
    svc.record_fault_lesson(_lesson())
    svc.sync_route_phase_weights({"P": 10.0}, "c", "h")
    assert (tmp_path / "reminders.json").exists()
    assert (tmp_path / ".nexus" / "knowledge" / "fault_lessons.jsonl").exists()
    assert (tmp_path / ".nexus" / "knowledge" / "policy_memory.jsonl").exists()


def test_memory_coordinator_lock_creates_no_file_under_switch(tmp_path, monkeypatch):
    from nexus.core.memory_coordinator import MemoryCoordinator

    coord = MemoryCoordinator()
    target = tmp_path / "sub" / "x.jsonl"
    monkeypatch.setenv(RO, "1")
    with coord.lock(target):
        pass
    with coord.lock(target, read_only=True):
        pass
    assert names(tmp_path) == []
    monkeypatch.delenv(RO)
    with coord.lock(target):
        pass
    assert (tmp_path / "sub" / "x.jsonl.lock").exists()


def test_findings_vector_sync_returns_false_when_skipped(tmp_path, monkeypatch):
    from nexus.research.findings_vector_sync import MemoryRepositoryFindingsVectorSync

    class _Repo:
        def semantic_dedup_ingest(self, table, payload):
            return MemoryRepository(tmp_path / "db").semantic_dedup_ingest(table, dict(payload))

    class _Registry:
        def repository_for(self, **kwargs):
            return _Repo()

    sync = MemoryRepositoryFindingsVectorSync(tmp_path, registry=_Registry())
    monkeypatch.setenv(RO, "1")
    assert sync.sync({"content": "c"}) is False
    assert names(tmp_path) == []


# ---- 5. SQLite snapshot consistency ----------------------------------------------------------


def test_snapshot_retries_when_source_changes_during_copy(tmp_path, monkeypatch):
    from nexus.core.memory_manager import ProjectMemoryManager as PMM

    mgr = ProjectMemoryManager(tmp_path)
    mgr.add_insight("t", "row")
    before = tree_hash(tmp_path)
    monkeypatch.setenv(RO, "1")
    ro = ProjectMemoryManager(tmp_path)
    real_copy = PMM._copy_snapshot
    calls = {"n": 0}

    def flaky_copy(self, tmpdir):
        real_copy(self, tmpdir)
        calls["n"] += 1
        if calls["n"] == 1:  # simulate a writer touching the source mid-copy
            import os

            st = os.stat(self.db_path)
            os.utime(self.db_path, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))

    monkeypatch.setattr(PMM, "_copy_snapshot", flaky_copy)
    assert [r[1] for r in ro.search("")] == ["row"]
    assert calls["n"] == 2
    # Only the mtime we nudged differs; content is unchanged.
    monkeypatch.undo()
    assert tree_hash(tmp_path) == before


def test_snapshot_persistent_change_raises_and_leaves_tree(tmp_path, monkeypatch):
    import glob
    import os
    import tempfile

    from nexus.core.memory_manager import ProjectMemoryManager as PMM
    from nexus.core.memory_manager import StateReadOnlySnapshotError

    ProjectMemoryManager(tmp_path).add_insight("t", "row")
    ro_env = monkeypatch
    ro_env.setenv(RO, "1")
    ro = ProjectMemoryManager(tmp_path)
    names_before = names(tmp_path)
    pattern = str(Path(tempfile.gettempdir()) / "nexus-ro-sqlite-*")
    temp_before = set(glob.glob(pattern))
    real_copy = PMM._copy_snapshot
    state = {"bump": 0}

    def always_changing(self, tmpdir):
        real_copy(self, tmpdir)
        state["bump"] += 1
        st = os.stat(self.db_path)
        os.utime(self.db_path, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000 * state["bump"]))

    monkeypatch.setattr(PMM, "_copy_snapshot", always_changing)
    with pytest.raises(StateReadOnlySnapshotError):
        ro.search("")
    assert state["bump"] == 3
    assert set(glob.glob(pattern)) == temp_before
    monkeypatch.undo()
    assert names(tmp_path) == names_before


# ---- 6. EpisodeRepository / PolicyMetabolizer / PolicyManager -----------------------------------


def _policy_rows():
    return [
        {"rule_id": "R1", "condition": "c", "action": "a", "confidence": 0.9},
        {
            "rule_id": "R2",
            "condition": "c2",
            "action": "a2",
            "confidence": 0.1,
            "created_at": "2000-01-01T00:00:00+00:00",
            "last_used_at": "2000-01-01T00:00:00+00:00",
        },
    ]


def test_episode_repository_noop_under_switch(tmp_path, monkeypatch):
    from nexus.core.episode_repository import EpisodeRepository

    repo = EpisodeRepository(str(tmp_path))
    monkeypatch.setenv(RO, "1")
    assert repo.append({"a": 1}) == repo.episode_file
    assert names(tmp_path) == []
    monkeypatch.delenv(RO)
    repo.append({"a": 1})
    for lock in tmp_path.rglob("*.lock"):
        lock.unlink()
    before = tree_hash(tmp_path)
    monkeypatch.setenv(RO, "1")
    repo.append({"a": 2})
    assert tree_hash(tmp_path) == before
    assert repo.episode_file.read_text().count("\n") == 1


def test_policy_metabolizer_noop_under_switch_and_unset_rewrites(tmp_path, monkeypatch):
    import json

    from nexus.core.policy_metabolizer import PolicyMetabolizer

    policy = tmp_path / ".nexus" / "knowledge" / "policy_memory.jsonl"
    policy.parent.mkdir(parents=True)
    policy.write_text("".join(json.dumps(r) + "\n" for r in _policy_rows()))
    before = tree_hash(tmp_path)
    monkeypatch.setenv(RO, "1")
    result = PolicyMetabolizer(str(tmp_path)).metabolize(force=True)
    assert result.scanned == 0 and result.snapshot_path is None
    assert tree_hash(tmp_path) == before
    monkeypatch.delenv(RO)
    result = PolicyMetabolizer(str(tmp_path)).metabolize(force=True)
    assert result.scanned == 2
    assert (tmp_path / ".nexus" / "knowledge" / "snapshots").exists()


def test_policy_manager_record_episode_writes_nothing_under_switch(tmp_path, monkeypatch):
    from nexus.core.policy_manager import PolicyManager
    from nexus.core.state_contracts import NexusState

    monkeypatch.setenv("NEXUS_MEMORY_AUTO_INIT", "0")
    manager = PolicyManager(str(tmp_path))
    state = NexusState(task_id="t1", task_description="t", project_root=str(tmp_path))
    state.metadata["episode_count"] = 5
    monkeypatch.setenv(RO, "1")
    manager.record_episode(state)
    assert state.metadata["metabolizer_status"] == "skipped_read_only"
    assert state.metadata.get("learning_ingest_status") in (
        None,
        "skipped_read_only",
        "skipped_frozen",
        "discarded",
        "export_model_queued",
    )
    assert state.metadata.get("learning_ingest_status") != "ingested"
    assert names(tmp_path) == []


def test_policy_manager_ingest_reports_skipped_under_switch(tmp_path, monkeypatch):
    from nexus.core.policy_manager import PolicyManager
    from nexus.core.state_contracts import NexusState

    monkeypatch.setenv("NEXUS_MEMORY_AUTO_INIT", "0")
    manager = PolicyManager(str(tmp_path))
    state = NexusState(task_id="t1", task_description="t", project_root=str(tmp_path))
    monkeypatch.setenv(RO, "1")
    manager._ingest_episode(state, {"task_id": "t1"}, "ingested")
    assert state.metadata["learning_ingest_status"] == "skipped_read_only"
    assert names(tmp_path) == []
