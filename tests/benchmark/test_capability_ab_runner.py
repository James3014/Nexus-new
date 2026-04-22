from __future__ import annotations

import json
from pathlib import Path

from scripts.bench.capability_ab_runner import (
    CapabilityTask,
    _extract_record,
    _extract_json_payload,
    _materialize_fixture,
    load_tasks,
    run_without_nexus,
    select_tasks,
)


def test_load_tasks_parses_capability_schema(tmp_path: Path):
    payload = {
        "tasks": [
            {
                "id": "hard-001",
                "difficulty": "hard",
                "task_type": "bug",
                "task_desc": "Fix race",
                "target_file": "a.py",
                "test_file": "tests/test_a.py",
                "success_criteria": "all_target_tests_pass",
            }
        ]
    }
    src = tmp_path / "tasks.json"
    src.write_text(json.dumps(payload), encoding="utf-8")
    tasks = load_tasks(src)
    assert len(tasks) == 1
    assert tasks[0].id == "hard-001"
    assert tasks[0].difficulty == "hard"


def test_materialize_fixture_writes_files(tmp_path: Path):
    task = CapabilityTask(
        id="easy-001",
        difficulty="easy",
        task_type="bug",
        task_desc="Fix text normalization",
        target_file="na",
        test_file="na",
        success_criteria="all_target_tests_pass",
    )
    target, test = _materialize_fixture(tmp_path, task)
    assert Path(target).exists()
    assert Path(test).exists()
    assert "normalize_flag" in Path(target).read_text(encoding="utf-8")


def test_extract_record_maps_semantic_fields():
    task = CapabilityTask(
        id="hard-001",
        difficulty="hard",
        task_type="bug",
        task_desc="Fix race",
        target_file="a.py",
        test_file="tests/test_a.py",
        success_criteria="all_target_tests_pass",
    )
    payload = {
        "status": "FAILED",
        "semantic_status": "UNVERIFIED",
        "runtime_classification": "runtime_defect",
        "result": {
            "elapsed_sec": 2.3,
            "report": {
                "attempt_count": 4,
                "model_calls": 1,
                "total_tokens": 321,
                "token_capture_status": "measured",
            },
        },
    }
    out = _extract_record(mode="with_nexus", task=task, payload=payload, wall_time_sec=2.5)
    assert out["task_id"] == "hard-001"
    assert out["semantic_status"] == "UNVERIFIED"
    assert out["attempt_count"] == 4
    assert out["model_calls"] == 1
    assert out["total_tokens"] == 321
    assert out["token_capture_status"] == "measured"
    assert out["report_trust_mismatch"] is False


def test_extract_json_payload_from_prefixed_output():
    raw = """Redis init failed
Memory warning
{
  "status": "SUCCESS",
  "semantic_status": "VERIFIED"
}"""
    payload = _extract_json_payload(raw)
    assert payload["status"] == "SUCCESS"
    assert payload["semantic_status"] == "VERIFIED"


def test_select_tasks_balances_buckets_for_all_mode():
    tasks = [
        CapabilityTask(id="easy-1", difficulty="easy", task_type="bug", task_desc="e1", target_file="a", test_file="b", success_criteria="x"),
        CapabilityTask(id="easy-2", difficulty="easy", task_type="bug", task_desc="e2", target_file="a", test_file="b", success_criteria="x"),
        CapabilityTask(id="medium-1", difficulty="medium", task_type="bug", task_desc="m1", target_file="a", test_file="b", success_criteria="x"),
        CapabilityTask(id="medium-2", difficulty="medium", task_type="bug", task_desc="m2", target_file="a", test_file="b", success_criteria="x"),
        CapabilityTask(id="hard-1", difficulty="hard", task_type="bug", task_desc="h1", target_file="a", test_file="b", success_criteria="x"),
        CapabilityTask(id="hard-2", difficulty="hard", task_type="bug", task_desc="h2", target_file="a", test_file="b", success_criteria="x"),
    ]
    selected = select_tasks(tasks, difficulty="all", max_tasks=6)
    assert [task.id for task in selected] == ["easy-1", "medium-1", "hard-1", "easy-2", "medium-2", "hard-2"]


def test_run_without_nexus_bare_mode_returns_record(tmp_path: Path):
    task = CapabilityTask(
        id="easy-001",
        difficulty="easy",
        task_type="bug",
        task_desc="Fix text normalization",
        target_file="unused",
        test_file="unused",
        success_criteria="all_target_tests_pass",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)
    out = run_without_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=10,
        force_flow=None,
        mode="bare",
    )
    assert out["mode"] == "without_nexus"
    assert out["semantic_status"] is None
    assert out["attempt_count"] == 1
    assert out["model_calls"] == 0
    assert out["total_tokens"] == 0
    assert out["token_capture_status"] == "not_applicable_local_only"


def test_run_without_nexus_bare_mode_hard_task_runs_verify_only(tmp_path: Path):
    task = CapabilityTask(
        id="hard-001",
        difficulty="hard",
        task_type="bug",
        task_desc="Fix flaky timeout race",
        target_file="unused",
        test_file="unused",
        success_criteria="all_target_tests_pass",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)
    out = run_without_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=10,
        force_flow=None,
        mode="bare",
    )
    assert out["status"] == "FAILED"
