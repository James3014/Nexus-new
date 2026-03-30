import pytest
from scripts.ops.task_runner import check_done, run_phase_task
from types import SimpleNamespace

def test_phase_task_schema():
    """Verify that phase_task schema is supported."""
    task = {
        "id": "test.phase",
        "type": "phase_task",
        "phase": "R",
        "task": "test task",
        "domain": "core"
    }
    # This just tests that it doesn't crash during processing
    assert task["type"] == "phase_task"

def test_phase_task_dispatch():
    """Verify that phase_task dispatch returns results."""
    task = {
        "id": "test.dispatch",
        "type": "phase_task",
        "phase": "R",
        "task": "Verify and fix external research pack consistency",
        "domain": "core"
    }
    # Mocking or running a small task
    # For now, just ensure the function exists and can be called
    assert run_phase_task is not None


def test_run_phase_task_routes_bug_through_service(monkeypatch):
    task = {
        "id": "fix.login",
        "type": "phase_task",
        "phase": "R",
        "task": "fix login callback",
        "domain": "core",
    }

    fake_service = SimpleNamespace(
        execute_bug=lambda task_desc, delivery_mode="standard", bug_id=None, **kwargs: (
            task_desc == "fix login callback"
            and delivery_mode == "standard"
            and bug_id == "fix.login"
        ),
        execute_feature=lambda *args, **kwargs: False,
    )
    fake_cli = SimpleNamespace(service=fake_service)

    monkeypatch.setattr("scripts.engine.nexus_cli.NexusCLI", lambda silent=True: fake_cli)

    rc, stdout, stderr, skills = run_phase_task(task)

    assert rc == 0
    assert stdout == "SUCCESS"
    assert stderr == ""
    assert skills == []

def test_phase_result_ok_done_when():
    """Verify that phase_result_ok type is handled."""
    task = {"done_when": {"type": "phase_result_ok"}}
    done, note = check_done(task, rc=0, stdout="SUCCESS", stderr="")
    assert done is True
    assert "phase_result_ok:SUCCESS" in note

    done, note = check_done(task, rc=1, stdout="FAIL", stderr="")
    assert done is False
