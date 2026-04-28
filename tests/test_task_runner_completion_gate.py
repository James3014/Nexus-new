from pathlib import Path

from scripts.ops import task_runner
from scripts.ops.task_runner import execute_single_task
from scripts.ops.task_runner import run_completion_gate_for_task


def test_run_completion_gate_for_task_writes_report(tmp_path: Path) -> None:
    task = {
        "id": "gate.pass",
        "completion_gate": {
            "task_level": "small_fix",
            "verify_commands": ["/bin/echo ok"],
            "output_dir": str(tmp_path / "delivery"),
        },
    }

    passed, note = run_completion_gate_for_task(task, {"require_completion_gate": False}, tmp_path)

    assert passed is True
    assert note == "verified"
    assert list((tmp_path / "delivery").glob("*.json"))
    assert list((tmp_path / "delivery").glob("*.md"))


def test_run_completion_gate_for_task_rejects_missing_required_config(
    tmp_path: Path,
) -> None:
    task = {"id": "gate.missing"}

    passed, note = run_completion_gate_for_task(task, {"require_completion_gate": True}, tmp_path)

    assert passed is False
    assert note == "completion_gate_missing"


def test_run_completion_gate_for_task_passes_delivery_profile_and_approval(tmp_path: Path) -> None:
    artifact = tmp_path / "live.json"
    artifact.write_text("{}", encoding="utf-8")
    task = {
        "id": "gate.live",
        "completion_gate": {
            "task_level": "feature",
            "delivery_profile": "live_browser",
            "verify_commands": ["/bin/echo ok-1", "/bin/echo ok-2"],
            "artifact_paths": [str(artifact)],
            "human_approval_refs": ["approved-by:james"],
            "output_dir": str(tmp_path / "delivery"),
        },
    }

    passed, note = run_completion_gate_for_task(task, {"require_completion_gate": False}, tmp_path)

    assert passed is True
    assert note == "verified"


def test_execute_single_task_does_not_mark_done_when_completion_gate_fails(
    monkeypatch,
) -> None:
    task = {
        "id": "gate.fail",
        "run": "/bin/echo ok",
        "type": "shell",
        "max_retry": 0,
    }
    state = {"tasks": {"gate.fail": {"status": "pending", "retry": 0}}}

    monkeypatch.setattr(
        "scripts.ops.task_runner.run_shell",
        lambda run_cmd, timeout_sec, cwd=None: (0, "ok", ""),
    )
    monkeypatch.setattr(
        "scripts.ops.task_runner.check_done",
        lambda task, rc, stdout, stderr: (True, "rc=0"),
    )
    monkeypatch.setattr(
        "scripts.ops.task_runner.run_completion_gate_for_task",
        lambda task, manifest_defaults, cwd=None: (False, "completion_gate_missing"),
    )
    monkeypatch.setattr("scripts.ops.task_runner.save_status", lambda state: None)
    monkeypatch.setattr("scripts.ops.task_runner.write_heartbeat", lambda state: None)
    monkeypatch.setattr(
        "scripts.ops.task_runner.incident_adapter.generate_report",
        lambda tid, diag_str: None,
    )

    result = execute_single_task(task, task["run"], {}, {}, state)

    assert result == "FAILED"
    assert state["tasks"]["gate.fail"]["status"] == "failed"
    assert "completion_gate_missing" in state["tasks"]["gate.fail"]["note"]


def test_task_runner_main_enables_high_delivery_mode(monkeypatch, tmp_path: Path) -> None:
    manifest = {
        "defaults": {},
        "tasks": [],
    }
    monkeypatch.setattr("scripts.ops.task_runner.acquire_lock", lambda lock_file: object())
    monkeypatch.setattr("scripts.ops.task_runner.release_lock", lambda lock_file, lock_fd: None)
    monkeypatch.setattr("scripts.ops.task_runner.load_config", lambda path: manifest if "task_manifest" in str(path) else {})
    captured = {}
    monkeypatch.setattr("scripts.ops.task_runner.save_status", lambda state: captured.update(state))
    monkeypatch.setattr("scripts.ops.task_runner.write_heartbeat", lambda state: None)
    monkeypatch.setattr("scripts.ops.task_runner.topo_sort", lambda tasks: tasks)
    monkeypatch.setattr("scripts.ops.task_runner.resolve_delivery_mode", lambda mode: "high")
    monkeypatch.setattr(
        "sys.argv",
        ["task_runner.py", "--delivery-mode", "ask"],
    )

    exit_code = task_runner.main()

    assert exit_code == 0
    assert captured["delivery_mode"] == "high"
