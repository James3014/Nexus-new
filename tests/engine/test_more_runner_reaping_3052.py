"""#3052: more runners of task, model or candidate commands leave no child behind.

The sandbox physical runner, direct-mode verify commands (taken from the task text), the
delivery gate's verification commands and the research flow's candidate test run started their
command without killing its process group after a normal exit. Each now goes through
``argv_command.run_reaping_process_group`` (or ``run_command_string(reap_process_group=True)``).
Every test starts a detached ``sleep`` that records its pid; the test asserts the pid is gone
once the entry point returns and kills it in ``finally`` if not (only pids this test started).
"""

from __future__ import annotations

import ast
import os
import signal
import subprocess
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def _gone(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    state = subprocess.run(
        ["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True, check=False
    ).stdout.strip()
    return not state or state.startswith("Z")


def _assert_reaped(pid_file: Path) -> None:
    for _ in range(100):
        if pid_file.exists() and pid_file.read_text().strip():
            break
        time.sleep(0.05)
    pid = int(pid_file.read_text().strip())
    try:
        deadline = time.monotonic() + 5
        while not _gone(pid) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert _gone(pid), f"background child {pid} outlived the run"
    finally:
        if not _gone(pid):
            os.kill(pid, signal.SIGKILL)


@pytest.fixture
def fake_pytest(tmp_path, monkeypatch):
    """A ``pytest`` on PATH that starts a detached child, records its pid and exits 0."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    pid_file = tmp_path / "bg.pid"
    script = bin_dir / "pytest"
    script.write_text(
        f"#!/bin/sh\n/bin/sleep 60 >/dev/null 2>&1 &\necho $! > '{pid_file}'\nexit 0\n"
    )
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '/usr/bin:/bin')}")
    project = (tmp_path / "project").resolve()
    project.mkdir()
    return project, pid_file


def test_sandbox_runner_task_command(tmp_path):
    from nexus.engine.sandbox_runner import SandboxRunner

    project = (tmp_path / "project").resolve()
    project.mkdir()
    pid_file = tmp_path / "bg.pid"
    runner = SandboxRunner(project)
    # The reaping does not depend on the OS barrier, which is macOS-only.
    runner.has_sandbox_exec = False
    result = runner.run_task(
        "detach",
        command=["/bin/sh", "-c", f"/bin/sleep 60 >/dev/null 2>&1 & echo $! > '{pid_file}'"],
        cwd=".",
        timeout_sec=20,
    )
    assert result["exit_code"] == 0, result
    _assert_reaped(pid_file)


def test_direct_mode_verify_command_from_the_task_text(fake_pytest):
    from nexus.engine import direct_mode

    project, pid_file = fake_pytest
    report = direct_mode.evaluate_direct_mode_completion(
        project_root=project, task_desc="Fix src/mod.py\npytest -q\n"
    )
    assert [item["exit_code"] for item in report["verify_results"]] == [0]
    _assert_reaped(pid_file)


def test_direct_mode_verify_command_is_bounded(fake_pytest, monkeypatch):
    from nexus.engine import direct_mode

    project, pid_file = fake_pytest
    script = project.parent / "bin" / "pytest"
    script.write_text(f"#!/bin/sh\n/bin/sleep 60 &\necho $! > '{pid_file}'\nwait\n")
    monkeypatch.setattr(direct_mode, "DIRECT_MODE_VERIFY_TIMEOUT_SECONDS", 1)
    report = direct_mode.evaluate_direct_mode_completion(
        project_root=project, task_desc="Fix src/mod.py\npytest -q\n"
    )
    assert "direct_mode_verify_error:pytest -q" in report["semantic_failures"]
    _assert_reaped(pid_file)


def test_delivery_gate_verification_command(fake_pytest):
    from nexus.delivery.gate import _run_verification_command

    project, pid_file = fake_pytest
    record = _run_verification_command("pytest -q", project)
    assert record.passed
    _assert_reaped(pid_file)


def test_research_flow_candidate_tests_default_to_the_reaping_runner():
    # The seed evaluation runs the candidate's tests (argv ``cmd``); an injected runner (tests)
    # still takes precedence.
    source = (REPO / "scripts/engine/commands/research_actions.py").read_text(encoding="utf-8")
    runners = {
        ast.unparse(node.func)
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.BoolOp)
        and node.args
        and ast.unparse(node.args[0]) == "cmd"
    }
    assert runners == {"subprocess_runner or run_reaping_process_group"}


def test_delivery_gate_verification_command_is_bounded(fake_pytest, monkeypatch):
    from nexus.delivery import gate

    project, pid_file = fake_pytest
    script = project.parent / "bin" / "pytest"
    script.write_text(f"#!/bin/sh\n/bin/sleep 60 &\necho $! > '{pid_file}'\nwait\n")
    monkeypatch.setattr(gate, "VERIFICATION_COMMAND_TIMEOUT_SECONDS", 1)
    record = gate._run_verification_command("pytest -q", project)
    assert (record.passed, record.exit_code) == (False, 124)
    _assert_reaped(pid_file)


def test_repair_loop_verify_step_uses_the_reaping_runner():
    # The CI gate dry-run runs the tests of the model-repaired tree.
    source = (REPO / "scripts/ops/autonomous_repair_loop.py").read_text(encoding="utf-8")
    calls = {
        ast.unparse(node.value.func)
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Assign)
        and [ast.unparse(target) for target in node.targets] == ["v_res"]
        and isinstance(node.value, ast.Call)
    }
    assert calls == {"run_reaping_process_group"}
