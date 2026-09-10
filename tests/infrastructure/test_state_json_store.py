from __future__ import annotations

import json
import multiprocessing
from pathlib import Path
from typing import Any

import pytest

from nexus.infrastructure.state_json_store import StateJsonStore


def test_compare_and_swap_creates_missing_file_and_reads_back(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    store = StateJsonStore()

    assert store.compare_and_swap_dict(path, None, {"value": 1}) is True
    assert store.read_dict(path) == {"value": 1}
    assert store.content_digest({"value": 1}) == store.content_digest(json.loads(path.read_text()))


def test_compare_and_swap_updates_existing_object(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    store = StateJsonStore()
    store.write_dict(path, {"value": 1})
    expected = store.content_digest({"value": 1})

    assert store.compare_and_swap_dict(path, expected, {"value": 2}) is True
    assert store.read_dict(path) == {"value": 2}


def test_compare_and_swap_rejects_stale_and_missing_expectations_without_change(
    tmp_path: Path,
) -> None:
    path = tmp_path / "state.json"
    store = StateJsonStore()
    store.write_dict(path, {})
    before = path.read_bytes()

    assert store.compare_and_swap_dict(path, None, {"value": 1}) is False
    assert (
        store.compare_and_swap_dict(path, store.content_digest({"wrong": 1}), {"value": 1}) is False
    )
    assert path.read_bytes() == before

    missing = tmp_path / "missing.json"
    assert store.compare_and_swap_dict(missing, store.content_digest({}), {"value": 1}) is False
    assert not missing.exists()


@pytest.mark.parametrize("raw", [b"not-json", json.dumps([]).encode(), b'{"value": NaN}'])
def test_compare_and_swap_rejects_corrupt_or_nonobject(tmp_path: Path, raw: bytes) -> None:
    path = tmp_path / "state.json"
    path.write_bytes(raw)
    with pytest.raises(ValueError):
        StateJsonStore().compare_and_swap_dict(path, None, {"value": 1})


def test_compare_and_swap_rejects_final_symlink(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    target.write_text("{}")
    path = tmp_path / "state.json"
    path.symlink_to(target)

    with pytest.raises(OSError):
        StateJsonStore().compare_and_swap_dict(path, None, {"value": 1})
    assert target.read_text() == "{}"


def _cas_worker(path_text: str, expected: str, barrier: Any, queue: Any) -> None:
    store = StateJsonStore()
    barrier.wait()
    queue.put(store.compare_and_swap_dict(Path(path_text), expected, {"winner": True}))


def test_two_processes_with_same_expected_only_one_succeeds(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    store = StateJsonStore()
    store.write_dict(path, {"winner": False})
    expected = store.content_digest({"winner": False})
    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(2)
    queue = context.Queue()
    processes = [
        context.Process(target=_cas_worker, args=(str(path), expected, barrier, queue))
        for _ in range(2)
    ]
    try:
        for process in processes:
            process.start()
        results = [queue.get(timeout=10) for _ in processes]
    finally:
        for process in processes:
            process.join(timeout=10)
            if process.is_alive():
                process.terminate()
                process.join(timeout=10)

    assert all(process.exitcode == 0 for process in processes)

    assert sorted(results) == [False, True]
    assert store.read_dict(path) == {"winner": True}


def test_compare_and_swap_replace_failure_preserves_original(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "state.json"
    store = StateJsonStore()
    store.write_dict(path, {"value": 1})
    before = path.read_bytes()
    expected = store.content_digest({"value": 1})

    def fail_replace(*_args, **_kwargs):
        raise OSError("simulated replace failure")

    monkeypatch.setattr("os.replace", fail_replace)
    with pytest.raises(OSError, match="simulated replace failure"):
        store.compare_and_swap_dict(path, expected, {"value": 2})
    assert path.read_bytes() == before


def test_compare_and_swap_rejects_readback_mismatch(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "state.json"
    store = StateJsonStore()
    store.write_dict(path, {"value": 1})
    expected = store.content_digest({"value": 1})
    original_read = StateJsonStore._read_dict_locked
    reads = 0

    def altered_read(current_store: StateJsonStore, read_path: Path):
        nonlocal reads
        reads += 1
        result = original_read(current_store, read_path)
        return {"value": 999} if reads == 2 else result

    monkeypatch.setattr(StateJsonStore, "_read_dict_locked", altered_read)
    with pytest.raises(RuntimeError, match="readback"):
        store.compare_and_swap_dict(path, expected, {"value": 2})


@pytest.mark.parametrize(
    "payload", [{"value": (1, 2)}, {1: "integer-key"}, {"value": float("nan")}]
)
def test_compare_and_swap_rejects_non_strict_json_payload_without_creating_or_changing(
    tmp_path: Path, payload: dict[Any, Any]
) -> None:
    store = StateJsonStore()
    missing = tmp_path / "missing.json"
    with pytest.raises((TypeError, ValueError)):
        store.compare_and_swap_dict(missing, None, payload)
    assert not missing.exists()

    path = tmp_path / "state.json"
    store.write_dict(path, {"original": True})
    before = path.read_bytes()
    with pytest.raises((TypeError, ValueError)):
        store.compare_and_swap_dict(path, store.content_digest({"original": True}), payload)
    assert path.read_bytes() == before


def test_compare_and_swap_freezes_nested_payload_before_lock(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "state.json"
    payload = {"nested": {"value": 1}}
    expected = StateJsonStore().content_digest({"old": True})
    original_locked = StateJsonStore._locked
    store = StateJsonStore()
    store.write_dict(path, {"old": True})

    def mutate_at_lock(store: StateJsonStore, lock_path: Path, *, shared: bool):
        payload["nested"]["value"] = 2
        return original_locked(store, lock_path, shared=shared)

    monkeypatch.setattr(StateJsonStore, "_locked", mutate_at_lock)
    assert store.compare_and_swap_dict(path, expected, payload) is True
    assert store.read_dict(path) == {"nested": {"value": 1}}


def test_compare_and_swap_rejects_invalid_unicode_before_filesystem_side_effect(
    tmp_path: Path,
) -> None:
    path = tmp_path / "nested" / "state.json"
    with pytest.raises(UnicodeEncodeError):
        StateJsonStore().compare_and_swap_dict(path, None, {"value": "\ud800"})
    assert not path.parent.exists()
