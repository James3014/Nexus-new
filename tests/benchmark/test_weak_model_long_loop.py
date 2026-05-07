from __future__ import annotations

import json
from pathlib import Path

from scripts.bench import weak_model_long_loop as loop


def _args(tmp_path: Path, tasks_file: Path):
    return type(
        "Args",
        (),
        {
            "tasks_file": str(tasks_file),
            "output_dir": str(tmp_path / "out"),
            "model_name": "gemini-3-flash-preview",
            "max_tasks": 2,
            "repeat_trials": 1,
            "timeout_sec": 300,
            "per_task_stop_loss_sec": 600,
            "total_timeout_sec": 7200,
        },
    )()


def test_build_plan_uses_twelve_task_fail_fast_shape(tmp_path: Path):
    tasks = tmp_path / "tasks.json"
    tasks.write_text(json.dumps([{"task_id": "a"}, {"task_id": "b"}, {"task_id": "c"}]), encoding="utf-8")

    plan = loop.build_plan(_args(tmp_path, tasks))

    assert plan["task_ids"] == ["a", "b"]
    assert plan["fail_fast"] == "stop_after_first_nonzero_or_with_nexus_semantic_failure"
    assert "--llm-candidate-cap" in plan["preflight_command"]
    assert plan["preflight_command"][plan["preflight_command"].index("--llm-candidate-cap") + 1] == "3"
    assert "--preflight-only" in plan["preflight_command"]
    assert plan["task_commands"][0]["command"][plan["task_commands"][0]["command"].index("--task-id-filter") + 1] == "a"


def test_run_plan_stops_on_first_failed_task(monkeypatch):
    calls = []

    class Result:
        def __init__(self, returncode: int):
            self.returncode = returncode

    def fake_run(cmd, env, check):
        calls.append(cmd)
        if "--preflight-only" in cmd:
            return Result(0)
        return Result(1 if len(calls) == 2 else 0)

    monkeypatch.setattr(loop.subprocess, "run", fake_run)
    plan = {
        "schema_version": "nexus_weak_model_long_loop_v1",
        "model_name": "gemini-3-flash-preview",
        "tasks_file": "tasks.json",
        "task_ids": ["a", "b"],
        "fail_fast": "stop_after_first_nonzero_or_with_nexus_semantic_failure",
        "preflight_command": ["runner", "--preflight-only"],
        "task_commands": [
            {"task_id": "a", "output_dir": "out/a", "command": ["runner", "a"]},
            {"task_id": "b", "output_dir": "out/b", "command": ["runner", "b"]},
        ],
    }

    result = loop.run_plan(plan, model_name="gemini-3-flash-preview", plan_only=False)

    assert result["execution_status"] == "stopped_on_failed_task"
    assert result["failed_task_id"] == "a"
    assert len(calls) == 2


def test_run_plan_stops_on_semantic_failure_even_when_process_succeeds(tmp_path: Path, monkeypatch):
    calls = []

    class Result:
        returncode = 0

    def fake_run(cmd, env, check):
        calls.append(cmd)
        if "--preflight-only" not in cmd:
            out = tmp_path / "out" / "a"
            out.mkdir(parents=True)
            (out / "with_nexus_1.jsonl").write_text(
                json.dumps(
                    {
                        "task_id": "a",
                        "semantic_status": "VERIFIED",
                        "run_eligible": False,
                        "infra_invalid_reason": "nexus_delivery_invalid",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
        return Result()

    monkeypatch.setattr(loop.subprocess, "run", fake_run)
    plan = {
        "schema_version": "nexus_weak_model_long_loop_v1",
        "model_name": "gemini-3-flash-preview",
        "tasks_file": "tasks.json",
        "task_ids": ["a", "b"],
        "fail_fast": "stop_after_first_nonzero_or_with_nexus_semantic_failure",
        "preflight_command": ["runner", "--preflight-only"],
        "task_commands": [
            {"task_id": "a", "output_dir": str(tmp_path / "out" / "a"), "command": ["runner", "a"]},
            {"task_id": "b", "output_dir": str(tmp_path / "out" / "b"), "command": ["runner", "b"]},
        ],
    }

    result = loop.run_plan(plan, model_name="gemini-3-flash-preview", plan_only=False)

    assert result["execution_status"] == "stopped_on_failed_task"
    assert result["failed_task_id"] == "a"
    assert result["failed_task_reason"] == "nexus_delivery_invalid"
    assert len(calls) == 2


def test_main_plan_only_writes_outputs(tmp_path: Path, monkeypatch):
    tasks = tmp_path / "tasks.json"
    output = tmp_path / "loop.md"
    output_json = tmp_path / "loop.json"
    tasks.write_text(json.dumps([{"task_id": "a"}]), encoding="utf-8")
    monkeypatch.setattr(
        "sys.argv",
        [
            "weak_model_long_loop.py",
            "--tasks-file",
            str(tasks),
            "--output-dir",
            str(tmp_path / "run"),
            "--plan-only",
            "--output",
            str(output),
            "--output-json",
            str(output_json),
        ],
    )

    assert loop.main() == 0
    assert "Nexus Weak Model Long Loop" in output.read_text(encoding="utf-8")
    assert json.loads(output_json.read_text(encoding="utf-8"))["execution_status"] == "plan_only"
