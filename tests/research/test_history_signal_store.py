import json
from pathlib import Path

from nexus.research.flow.history_signal_store import HistorySignalStore, auto_flow_key


def _history_path(root: Path) -> Path:
    path = root / ".nexus" / "reports" / "research" / "auto-flow-history.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def test_history_signal_store_matches_recent_success(tmp_path):
    _history_path(tmp_path).write_text(
        json.dumps(
            {
                "flow:hyper": [
                    {
                        "flow": "hyper_sprint",
                        "status": "SUCCESS",
                        "reason": "stage1_pass",
                        "task_type": "bug",
                        "task_desc": "fix websocket timeout race in coordinator",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    out = HistorySignalStore(tmp_path).load_memory_signal(
        task_desc="fix websocket timeout race in orchestrator",
        task_type="bug",
    )

    assert out["memory_hits"] == 1
    assert out["memory_hints"] == ["flow:hyper_sprint", "reason:stage1_pass"]
    assert out["processed_entries"] == 1


def test_history_signal_store_bounds_processed_entries(tmp_path):
    entries = [
        {
            "flow": "baseline",
            "status": "SUCCESS",
            "reason": "old_match",
            "task_type": "bug",
            "task_desc": "fix websocket timeout race in coordinator",
        }
    ]
    entries.extend(
        {
            "flow": "baseline",
            "status": "SUCCESS",
            "reason": f"recent_{idx}",
            "task_type": "bug",
            "task_desc": "fix invoice rounding drift",
        }
        for idx in range(20)
    )
    _history_path(tmp_path).write_text(json.dumps({"items": entries}), encoding="utf-8")

    out = HistorySignalStore(tmp_path, max_entries=5).load_memory_signal(
        task_desc="fix websocket timeout race in orchestrator",
        task_type="bug",
    )

    assert out["processed_entries"] == 5
    assert out["memory_hits"] == 0


def test_history_signal_store_corrupt_or_oversized_history_fails_closed(tmp_path):
    path = _history_path(tmp_path)
    path.write_text("{not-json", encoding="utf-8")
    assert HistorySignalStore(tmp_path).load_memory_signal(task_desc="fix race", task_type="bug")[
        "memory_hits"
    ] == 0

    path.write_text(json.dumps({"items": []}), encoding="utf-8")
    assert HistorySignalStore(tmp_path, max_bytes=1).load_memory_signal(
        task_desc="fix race",
        task_type="bug",
    )["memory_hits"] == 0


def test_history_signal_store_loads_and_writes_flow_history(tmp_path):
    store = HistorySignalStore(tmp_path)
    key = auto_flow_key("nexus/foo.py", "tests/test_foo.py")

    assert key == "nexus/foo.py|tests/test_foo.py"
    assert store.load_payload() == {}
    assert store.recent_for(target_file="nexus/foo.py", test_file="tests/test_foo.py") == []

    payload = store.write_recent_for(
        target_file="nexus/foo.py",
        test_file="tests/test_foo.py",
        recent=[
            {"status": "OLD", "flow": "baseline"},
            {"status": "SUCCESS", "flow": "hyper_sprint"},
        ],
        max_items=1,
    )

    assert payload[key] == [{"status": "SUCCESS", "flow": "hyper_sprint"}]
    assert store.load_payload()[key] == [{"status": "SUCCESS", "flow": "hyper_sprint"}]
    assert store.recent_for(target_file="nexus/foo.py", test_file="tests/test_foo.py") == [
        {"status": "SUCCESS", "flow": "hyper_sprint"}
    ]
