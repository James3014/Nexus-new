import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from nexus.events.log_store import JsonlEventLogStore
from nexus.events.writer_generation import (
    EventWriterGeneration,
    GenerationConflict,
    GenerationError,
    install_generation,
    manifest_path,
)


def record(sequence=1):
    return {
        "event_type": "attempt_transition",
        "timestamp": 1.0,
        "seq": sequence,
        "payload": {
            "task_id": "fence-task",
            "attempt_id": "fence-attempt",
            "sequence": sequence,
            "state": "VERIFY",
        },
    }


def configured(root: Path, generation=1, writer="writer-a"):
    token = EventWriterGeneration(generation, writer)
    install_generation(root, token, expected_generation=None if generation == 1 else generation - 1)
    store = JsonlEventLogStore()
    store.configure(root, writer_generation=token, enforce_generation=True)
    return store, token


def test_install_cas_manifest_and_restart_digest(tmp_path):
    store, token = configured(tmp_path)
    path = tmp_path / ".nexus" / "events" / "event_log.jsonl"
    store.append_record(record())
    before = path.read_bytes()
    assert json.loads(manifest_path(tmp_path).read_text())["generation"] == 1
    reopened = JsonlEventLogStore()
    reopened.configure(tmp_path, writer_generation=token, enforce_generation=True)
    assert reopened.attempt_tail("fence-task", "fence-attempt") == 1
    after = path.read_bytes() if path.exists() else b""
    assert after == before
    with pytest.raises(GenerationConflict, match="GENERATION_CAS_CONFLICT"):
        install_generation(tmp_path, EventWriterGeneration(2, "writer-b"), expected_generation=None)


def test_stale_handle_and_unfenced_legacy_writer_are_denied_without_bytes(tmp_path):
    store, token = configured(tmp_path)
    install_generation(tmp_path, EventWriterGeneration(2, "writer-b"), expected_generation=1)
    path = tmp_path / ".nexus" / "events" / "event_log.jsonl"
    before = path.read_bytes() if path.exists() else b""
    with pytest.raises(GenerationError, match="GENERATION_REQUIRED|GENERATION_TOKEN_MISMATCH"):
        store.append_record(record())
    after = path.read_bytes() if path.exists() else b""
    assert after == before
    with pytest.raises(GenerationError, match="GENERATION_REQUIRED"):
        JsonlEventLogStore().configure(tmp_path)


@pytest.mark.parametrize("kind", ["missing", "malformed", "symlink"])
def test_missing_malformed_and_symlink_manifest_fail_closed(tmp_path, kind):
    events = tmp_path / ".nexus" / "events"
    events.mkdir(parents=True)
    if kind == "malformed":
        manifest_path(tmp_path).write_text("{broken", encoding="utf-8")
    elif kind == "symlink":
        target = tmp_path / "outside.json"
        target.write_text(json.dumps({}), encoding="utf-8")
        manifest_path(tmp_path).symlink_to(target)
    store = JsonlEventLogStore()
    if kind == "missing":
        with pytest.raises(GenerationError, match="GENERATION_TOKEN_MISMATCH"):
            store.configure(tmp_path, writer_generation=EventWriterGeneration(1, "w"), enforce_generation=True)
    else:
        with pytest.raises(GenerationError):
            store.configure(tmp_path)


def test_dangling_manifest_and_lock_symlinks_fail_closed(tmp_path):
    events = tmp_path / ".nexus" / "events"
    events.mkdir(parents=True)
    manifest_path(tmp_path).symlink_to(events / "missing-manifest.json")
    with pytest.raises(GenerationError, match="GENERATION_MANIFEST_SYMLINK"):
        JsonlEventLogStore().configure(tmp_path)

    manifest_path(tmp_path).unlink()
    lock = events / "event_log.lock"
    lock.unlink()
    lock.symlink_to(events / "missing-lock")
    with pytest.raises(GenerationError, match="GENERATION_LOCK_UNSAFE"):
        install_generation(tmp_path, EventWriterGeneration(1, "writer"))


def test_lock_symlink_denies_append_and_boolean_cas_is_malformed(tmp_path):
    store, _ = configured(tmp_path)
    lock = tmp_path / ".nexus" / "events" / "event_log.lock"
    lock.unlink()
    lock.symlink_to(tmp_path / "missing-lock")
    with pytest.raises(GenerationError, match="GENERATION_LOCK_UNSAFE"):
        store.append_record(record())
    lock.unlink()
    with pytest.raises(GenerationError, match="GENERATION_CAS_MALFORMED"):
        install_generation(tmp_path, EventWriterGeneration(2, "writer-b"), expected_generation=True)


def test_nonregular_lock_and_configure_state_switch_are_bounded(tmp_path):
    root = tmp_path / "root"
    store = JsonlEventLogStore()
    store.configure(root)
    lock = root / ".nexus" / "events" / "event_log.lock"
    lock.unlink()
    os.mkfifo(lock)
    started = time.monotonic()
    with pytest.raises(GenerationError, match="GENERATION_LOCK_UNSAFE"):
        store.append_record(record())
    assert time.monotonic() - started < 2

    root_b = tmp_path / "root-b"
    finished = threading.Event()
    with store._lock:
        thread = threading.Thread(target=lambda: (store.configure(root_b), finished.set()))
        thread.start()
        assert not finished.wait(0.1)
        assert store.event_log_path == root / ".nexus" / "events" / "event_log.jsonl"
    thread.join(timeout=5)
    assert finished.is_set()
    assert store.event_log_path == root_b / ".nexus" / "events" / "event_log.jsonl"


def test_cross_process_competing_writers_same_generation(tmp_path):
    token = EventWriterGeneration(1, "shared")
    install_generation(tmp_path, token)
    script = """
import sys
from pathlib import Path
from nexus.events.log_store import JsonlEventLogStore
from nexus.events.writer_generation import EventWriterGeneration
root=Path(sys.argv[1]); task=sys.argv[2]; store=JsonlEventLogStore(); store.configure(root, writer_generation=EventWriterGeneration(1, 'shared'), enforce_generation=True)
store.append_record({'event_type':'attempt_transition','timestamp':1.0,'seq':1,'payload':{'task_id':task,'attempt_id':'a','sequence':1,'state':'VERIFY'}})
"""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2])
    processes = [subprocess.Popen([sys.executable, "-c", script, str(tmp_path), f"race-{index}"], env=env) for index in range(2)]
    assert sorted(p.wait(timeout=10) for p in processes) == [0, 0]
    rows = (tmp_path / ".nexus" / "events" / "event_log.jsonl").read_text().splitlines()
    assert len(rows) == 2
    assert all(json.loads(row)["_writer_generation"] == 1 for row in rows)
