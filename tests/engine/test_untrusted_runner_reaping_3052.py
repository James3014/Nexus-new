"""#3052: runners of candidate or agent-claimed commands leave no child behind.

These entry points ran model-written code, candidate tests or commands an agent claimed in its
evidence with a plain ``subprocess.run``: a background child that closed its output kept running
after a normal exit, and a timeout killed only the direct child. Each now goes through
``argv_command.run_reaping_process_group``. Every test here runs a command that starts a
detached ``sleep`` and records its pid; the test asserts that pid is gone once the entry point
returns, and kills it in ``finally`` if it is not (only pids this test started are signalled).
"""

from __future__ import annotations

import ast
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from nexus.core import argv_command

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


def _background_pid(pid_file: Path) -> int:
    for _ in range(100):
        text = pid_file.read_text().strip() if pid_file.exists() else ""
        if text:
            return int(text)
        time.sleep(0.05)
    raise AssertionError("the command did not record its background child")


def _assert_reaped(pid_file: Path) -> None:
    pid = _background_pid(pid_file)
    try:
        deadline = time.monotonic() + 5
        while not _gone(pid) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert _gone(pid), f"background child {pid} outlived the run"
    finally:
        if not _gone(pid):
            os.kill(pid, signal.SIGKILL)


def _detach(pid_file: Path) -> list[str]:
    """argv that starts a detached sleep, records its pid and exits 0 at once."""
    return ["/bin/sh", "-c", f"/bin/sleep 60 >/dev/null 2>&1 & echo $! > '{pid_file}'"]


@pytest.fixture
def fake_runner(tmp_path, monkeypatch):
    """``pytest`` and ``uv`` on PATH that start a detached child and exit 0 (allowlisted
    prefixes, so the evidence replay paths run them)."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    pid_file = tmp_path / "bg.pid"
    body = f"#!/bin/sh\n/bin/sleep 60 >/dev/null 2>&1 &\necho $! > '{pid_file}'\nexit 0\n"
    for name in ("pytest", "uv"):
        script = bin_dir / name
        script.write_text(body)
        script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '/usr/bin:/bin')}")
    project = (tmp_path / "project").resolve()
    project.mkdir()
    return project, pid_file


def test_evidence_verifier_replay_of_a_claimed_test_command(fake_runner):
    from nexus.delivery.evidence_verifier import EvidenceVerifier

    project, pid_file = fake_runner
    report = EvidenceVerifier(project)._verify_test_commands(["pytest -q"])
    assert [item["exit_code"] for item in report["executed"]] == [0]
    _assert_reaped(pid_file)


def test_evidence_verifier_test_collection(fake_runner):
    from nexus.delivery.evidence_verifier import collect_test_ids

    project, pid_file = fake_runner
    ids, reason = collect_test_ids(("pytest",), [], project)
    assert (ids, reason) == ([], "")
    _assert_reaped(pid_file)


def test_replay_runner_replay_of_a_claimed_command(fake_runner):
    from nexus.delivery.replay_runner import ReplayRunner

    project, pid_file = fake_runner
    result = ReplayRunner(project).run_replay({
        "test_artifacts": [{"command": "pytest -q", "exit_code": 0}]
    })
    assert [item["status"] for item in result["replay_results"]] == ["EXECUTED"]
    _assert_reaped(pid_file)


def test_autonomous_repair_loop_model_proposed_command(fake_runner):
    from scripts.ops.autonomous_repair_loop import execute_repair_proposals

    project, pid_file = fake_runner
    outcomes = execute_repair_proposals(["pytest -q"], project)
    assert outcomes == [{"command": "pytest -q", "status": "EXECUTED", "exit_code": 0}]
    _assert_reaped(pid_file)


def test_day_shift_candidate_tests(fake_runner):
    from nexus.research.day_shift_optimizer import DayShiftOptimizer

    project, pid_file = fake_runner
    optimizer = SimpleNamespace(swarm_dir=project, test_timeout_sec=20)
    assert DayShiftOptimizer._run_tests(optimizer)[0] == 0  # pyright: ignore[reportArgumentType]
    _assert_reaped(pid_file)


def test_nightshift_candidate_checks(tmp_path):
    from nexus.app.nightshift_runner_service import AutoResearchNightShift

    pid_file = tmp_path / "bg.pid"
    ok, _message = AutoResearchNightShift._run_cmd(
        None,  # pyright: ignore[reportArgumentType]
        _detach(pid_file),
        tmp_path,
        20,
    )
    assert ok
    _assert_reaped(pid_file)


def test_research_flow_visible_test_outside_the_confined_lane(tmp_path, monkeypatch):
    from nexus.app import research_flow_service
    from nexus.services import post_candidate_seam

    monkeypatch.setattr(post_candidate_seam, "confine_visible_test_enabled", lambda: False)
    pid_file = tmp_path / "bg.pid"
    completed = research_flow_service._run_visible_pytest(
        _detach(pid_file),
        repo_root=tmp_path,
        target_path=tmp_path / "mod.py",
        test_path=tmp_path / "test_mod.py",
        original_code="",
        candidate_code="",
        timeout_sec=20,
    )
    assert completed.returncode == 0
    _assert_reaped(pid_file)


def test_sprint_in_place_candidate_tests(tmp_path, monkeypatch):
    from nexus.research.sprint_service import InPlaceSprintExecutor
    from nexus.services import post_candidate_seam

    monkeypatch.setattr(post_candidate_seam, "confine_visible_test_enabled", lambda: False)
    repo = (tmp_path / "repo").resolve()
    repo.mkdir()
    (repo / "mod.py").write_text("VALUE = 1\n")
    pid_file = tmp_path / "bg.pid"
    executor = InPlaceSprintExecutor(repo, "mod.py", _detach(pid_file), 20)
    result = executor.evaluate_candidate(seed=0, hint="", code="VALUE = 2\n", source="test")
    assert result.score == 1.0, result.error
    _assert_reaped(pid_file)
    assert (repo / "mod.py").read_text() == "VALUE = 1\n"


def test_external_intelligence_closure_non_pytest_verifier(tmp_path):
    from nexus.services.external_intelligence_closure import (
        UNIT_VERIFICATION_SCHEMA,
        _run_verifier_specs,
    )

    root = (tmp_path / "repo").resolve()
    root.mkdir()

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, check=True
        ).stdout.strip()

    git("init", "-q")
    git("config", "user.email", "nexus-test@example.invalid")
    git("config", "user.name", "Nexus Test")
    git("config", "commit.gpgsign", "false")
    (root / "mod.py").write_text("VALUE = 1\n")
    git("add", "-A")
    git("commit", "-q", "-m", "base")
    base = git("rev-parse", "HEAD")
    (root / "mod.py").write_text("VALUE = 2\n")
    git("add", "-A")
    git("commit", "-q", "-m", "candidate")
    candidate = git("rev-parse", "HEAD")
    pid_file = tmp_path / "bg.pid"
    verification = _run_verifier_specs(
        task_id="t-3052",
        unit_id="u-3052",
        workspace_path=str(root),
        candidate_commit=candidate,
        specs=[{"id": "detach", "argv": _detach(pid_file)}],
        schema=UNIT_VERIFICATION_SCHEMA,
        scope="UNIT",
        base_sha=base,
        authorized_paths=["mod.py"],
        deletable_paths=(),
    )
    (row,) = verification["results"]
    assert row["returncode"] == 0, row
    _assert_reaped(pid_file)


def test_helper_passes_stdin_and_refuses_a_pipe(tmp_path):
    completed = argv_command.run_reaping_process_group(
        ["/bin/sh", "-c", "cat"], stdin=subprocess.DEVNULL, timeout=20
    )
    assert (completed.returncode, completed.stdout) == (0, "")
    with pytest.raises(ValueError, match="stdin=PIPE"):
        argv_command.run_reaping_process_group(["/bin/true"], stdin=subprocess.PIPE)


# Functions that run candidate code, candidate tests or commands an agent claimed. None of them
# may call subprocess.run (or Popen) directly again: that is how this bug class came back.
_REAPING_ENTRY_POINTS = {
    "nexus/delivery/evidence_verifier.py": ["collect_test_ids", "_verify_test_commands"],
    "nexus/delivery/replay_runner.py": ["run_replay"],
    "nexus/orchestrator/governed_integration.py": ["integrate_authorized_task_state"],
    "nexus/app/research_flow_service.py": ["_run_visible_pytest"],
    "nexus/app/nightshift_runner_service.py": ["_run_cmd"],
    "nexus/research/sprint_service.py": ["_evaluate"],
    "nexus/research/day_shift_optimizer.py": ["_run_tests"],
    "nexus/services/external_intelligence_closure.py": ["_run_one_verifier"],
    "scripts/ops/autonomous_repair_loop.py": ["execute_repair_proposals"],
}


def _direct_subprocess_calls(node: ast.AST) -> list[str]:
    found = []
    for call in ast.walk(node):
        if not isinstance(call, ast.Call):
            continue
        func = call.func
        if (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "subprocess"
            and func.attr in {"run", "Popen", "call", "check_call", "check_output"}
        ):
            found.append(f"subprocess.{func.attr} at line {call.lineno}")
    return found


@pytest.mark.parametrize("path", sorted(_REAPING_ENTRY_POINTS))
def test_entry_points_do_not_call_subprocess_directly(path):
    tree = ast.parse((REPO / path).read_text(encoding="utf-8"))
    functions = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    for name in _REAPING_ENTRY_POINTS[path]:
        assert name in functions, f"{path}: {name} not found (renamed? update this list)"
        assert "run_reaping_process_group" in ast.unparse(functions[name]), f"{path}: {name}"
        assert _direct_subprocess_calls(functions[name]) == [], f"{path}: {name}"


def test_replay_runner_loaded_by_path_under_a_bare_python_still_reaps(tmp_path):
    # scripts/ops/replay_runner.py loads nexus/delivery/replay_runner.py by path under a bare
    # python3 in the delivery gate, where the nexus package is not importable.
    code = (
        "import importlib.util, sys\n"
        f"spec = importlib.util.spec_from_file_location('rr', {str(REPO / 'nexus/delivery/replay_runner.py')!r})\n"
        "module = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(module)\n"
        "assert 'nexus' not in sys.modules\n"
        "print(module.run_reaping_process_group.__name__)\n"
    )
    completed = subprocess.run(
        [sys.executable, "-I", "-S", "-c", code],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert (completed.returncode, completed.stdout) == (0, "run_reaping_process_group\n"), (
        completed.stderr
    )
