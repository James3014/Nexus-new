from __future__ import annotations

import json
from pathlib import Path

from scripts.bench.capability_ab_runner import load_tasks
from scripts.bench.capability_ab_runner import _materialize_fixture


def test_rlm_harder_manifest_targets_recursive_reasoning_gaps():
    path = Path("scripts/bench/public_benchmark_rlm_harder_v1.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    tasks = payload["tasks"]

    assert payload["frozen"] is True
    assert payload["benchmark_id"] == "nexus-public-rlm-harder-v1"
    assert len(tasks) == 4
    assert {task["category"] for task in tasks} == {
        "docs_code_sync",
        "feature",
        "ops_research",
        "test_repair",
    }
    assert {task["rlm_challenge"] for task in tasks} == {
        "multi_file",
        "long_context",
        "misleading_tests",
        "second_round_diagnosis",
    }
    assert all(task["repo_kind"] == "neutral_fixture" for task in tasks)
    assert all(task["success_criteria"] == "patch_and_tests_pass" for task in tasks)
    assert all(task["mutation_required"] is True for task in tasks)
    assert all(task["fixture_kind"].startswith("rlm_harder_") for task in tasks)

    loaded = load_tasks(path)
    assert [task.id for task in loaded] == [task["id"] for task in tasks]
    assert all(len(task.manifest_hash) == 64 for task in loaded)


def test_rlm_harder_manifest_uses_dedicated_fixtures(tmp_path: Path):
    tasks = load_tasks("scripts/bench/public_benchmark_rlm_harder_v1.json")

    signatures = set()
    for task in tasks:
        target, test = _materialize_fixture(tmp_path, task)
        target_source = Path(target).read_text(encoding="utf-8")
        test_source = Path(test).read_text(encoding="utf-8")
        signatures.add((target_source, test_source))
        assert task.fixture_kind.startswith("rlm_harder_")
        assert "rlm_harder" in target_source
        assert "spec_from_file_location" in test_source

    assert len(signatures) == len(tasks)


def test_rlm_harder_v2_manifest_uses_hidden_verifier_challenges(tmp_path: Path):
    path = Path("scripts/bench/public_benchmark_rlm_harder_v2.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    tasks = payload["tasks"]

    assert payload["benchmark_id"] == "nexus-public-rlm-harder-v2"
    assert payload["frozen"] is True
    assert len(tasks) == 8
    assert {task["rlm_challenge"] for task in tasks} == {
        "hidden_governance",
        "hidden_evidence",
        "hidden_second_round",
        "hidden_memory_contract",
        "hidden_belief_budget",
    }
    challenge_counts: dict[str, int] = {}
    for task in tasks:
        challenge = task["rlm_challenge"]
        challenge_counts[challenge] = challenge_counts.get(challenge, 0) + 1
    assert challenge_counts["hidden_governance"] >= 2
    assert challenge_counts["hidden_evidence"] >= 2
    assert challenge_counts["hidden_memory_contract"] + challenge_counts["hidden_belief_budget"] >= 2
    assert all(task["fixture_kind"].startswith("rlm_harder_v2_") for task in tasks)

    for task in load_tasks(path):
        target, test = _materialize_fixture(tmp_path, task)
        target_source = Path(target).read_text(encoding="utf-8")
        test_source = Path(test).read_text(encoding="utf-8")
        assert "rlm_harder_v2" in target_source
        assert "spec_from_file_location" in test_source
