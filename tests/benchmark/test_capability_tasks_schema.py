from __future__ import annotations

import json
from pathlib import Path


def test_capability_tasks_v1_has_balanced_buckets():
    path = Path("scripts/bench/capability_tasks_v1.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    tasks = payload["tasks"]
    assert len(tasks) == 30

    by_difficulty = {"easy": 0, "medium": 0, "hard": 0}
    ids: set[str] = set()
    required_keys = {"id", "difficulty", "task_type", "task_desc", "target_file", "test_file", "success_criteria"}

    for task in tasks:
        assert required_keys.issubset(task.keys())
        assert task["id"] not in ids
        ids.add(task["id"])
        by_difficulty[task["difficulty"]] += 1

    assert by_difficulty["easy"] == 10
    assert by_difficulty["medium"] == 10
    assert by_difficulty["hard"] == 10


def test_cross_module_capability_tasks_schema():
    path = Path("scripts/bench/capability_tasks_cross_module_v1.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    tasks = payload["tasks"]
    assert len(tasks) == 12
    required_keys = {"id", "difficulty", "task_type", "task_desc", "target_file", "test_file", "success_criteria"}
    buckets = {"swarm": 0, "drone": 0, "nightshift": 0}
    for task in tasks:
        assert required_keys.issubset(task.keys())
        assert task["difficulty"] == "hard"
        assert task["task_type"].startswith("cross_module_refactor_")
        if task["task_type"].endswith("_swarm"):
            buckets["swarm"] += 1
        if task["task_type"].endswith("_drone"):
            buckets["drone"] += 1
        if task["task_type"].endswith("_nightshift"):
            buckets["nightshift"] += 1
    assert buckets == {"swarm": 4, "drone": 4, "nightshift": 4}
