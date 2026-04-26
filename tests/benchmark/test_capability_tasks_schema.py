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
        assert Path(task["target_file"]).exists()
        assert Path(task["test_file"]).exists()
        if task["task_type"].endswith("_swarm"):
            buckets["swarm"] += 1
        if task["task_type"].endswith("_drone"):
            buckets["drone"] += 1
        if task["task_type"].endswith("_nightshift"):
            buckets["nightshift"] += 1
    assert buckets == {"swarm": 4, "drone": 4, "nightshift": 4}


def test_public_benchmark_pilot_manifest_distribution():
    path = Path("scripts/bench/public_benchmark_pilot_v1.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    tasks = payload["tasks"]
    assert len(tasks) == 30
    assert payload["frozen"] is True

    required = {
        "id",
        "category",
        "difficulty",
        "repo_kind",
        "repo",
        "repo_ref",
        "task_desc",
        "success_criteria",
        "mutation_required",
        "allowed_files",
        "forbidden_files",
        "setup_command",
        "verification_command",
    }
    categories = {
        "bugfix": 0,
        "test_repair": 0,
        "refactor": 0,
        "feature": 0,
        "docs_code_sync": 0,
        "ops_research": 0,
    }
    repo_kinds = {"nexus_internal": 0, "neutral_fixture": 0, "external": 0}
    ids: set[str] = set()

    for task in tasks:
        assert required.issubset(task.keys())
        assert task["id"] not in ids
        ids.add(task["id"])
        assert task["success_criteria"] == "patch_and_tests_pass"
        assert task["mutation_required"] is True
        assert task["allowed_files"]
        assert task["forbidden_files"]
        if task["repo_kind"] == "nexus_internal":
            assert Path(task["target_file"]).exists()
            assert Path(task["test_file"]).exists()
        else:
            assert task.get("fixture_kind") or task["repo"].startswith("https://")
        categories[task["category"]] += 1
        repo_kinds[task["repo_kind"]] += 1

    assert categories == {
        "bugfix": 5,
        "test_repair": 5,
        "refactor": 5,
        "feature": 5,
        "docs_code_sync": 5,
        "ops_research": 5,
    }
    assert repo_kinds["nexus_internal"] == 6
    assert repo_kinds["neutral_fixture"] == 18
    assert repo_kinds["external"] == 6
    assert (repo_kinds["neutral_fixture"] + repo_kinds["external"]) / len(tasks) == 0.8


def test_public_hard_neutral_v2_manifest_has_12_unique_hard_tasks():
    path = Path("scripts/bench/public_benchmark_hard_neutral_v2.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    tasks = payload["tasks"]
    assert len(tasks) == 12
    assert payload["frozen"] is True

    categories = {
        "bugfix": 0,
        "test_repair": 0,
        "refactor": 0,
        "feature": 0,
        "docs_code_sync": 0,
        "ops_research": 0,
    }
    ids: set[str] = set()

    for task in tasks:
        assert task["id"] not in ids
        ids.add(task["id"])
        assert task["difficulty"] == "hard"
        assert task["repo_kind"] == "neutral_fixture"
        assert task["fixture_kind"]
        assert task["success_criteria"] == "patch_and_tests_pass"
        assert task["mutation_required"] is True
        categories[task["category"]] += 1

    assert categories == {
        "bugfix": 2,
        "test_repair": 2,
        "refactor": 2,
        "feature": 2,
        "docs_code_sync": 2,
        "ops_research": 2,
    }
