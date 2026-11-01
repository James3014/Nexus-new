"""#3052 batch 4b: the DSH turn runner and gates, the CI gate steps and the repair loop's verify
step kill their process group and are bounded.

- ``nexus-dsh-workflow`` ``_run_dsh_supervised`` (a DSH coding-agent turn) ran DSH in the
  caller's process group, read its output with ``readline`` until EOF (held open by any
  background child) and had no wall clock.
- Its red/green gates (``_run_red_tests``, ``_run_pytest``) and the ruff runs over candidate
  files used ``subprocess.run``: a candidate test's background child outlived the gate.
- ``ci_gate.run_step`` used ``shell=True`` with no timeout; the repair loop's verify step had
  no timeout.

Every test starts a fake command whose background grandchild (a double fork that stays in the
command's process group) records its pid in this test's tmp dir; only that pid is ever
signalled, and only while ``ps`` shows this test's own tmp path in its command line.
"""

from __future__ import annotations

import argparse
import ast
import os
import signal
import subprocess
import sys
import time
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

dsh = SourceFileLoader(
    "nexus_dsh_workflow_reaping_3052_batch4b", str(REPO / "scripts" / "ops" / "nexus-dsh-workflow")
).load_module()

# A command that prints FIRST_LINE, leaves a grandchild in its own process group (detached
# from its output, or holding it with HOLD), waits until the grandchild has recorded its pid,
# then sleeps LINGER seconds (exiting 0 on SIGTERM, like the installed DSH) and exits EXIT_CODE.
FAKE = r"""#!{python}
import os, signal, sys, time
PIDFILE = {pidfile!r}
print({first_line!r}, flush=True)
pid = os.fork()
if pid == 0:
    if os.fork() == 0:
        if not {hold!r}:
            null = os.open(os.devnull, os.O_RDWR)
            for fd in (0, 1, 2):
                os.dup2(null, fd)
        with open(PIDFILE + ".tmp", "w") as fh:
            fh.write(str(os.getpid()))
        os.replace(PIDFILE + ".tmp", PIDFILE)
        time.sleep(60)
        os._exit(0)
    os._exit(0)
os.waitpid(pid, 0)
while not os.path.exists(PIDFILE):
    time.sleep(0.01)
signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
time.sleep({linger!r})
sys.exit({exit_code!r})
"""


def _fake(
    tmp_path: Path,
    name: str,
    *,
    hold: bool = False,
    linger: float = 0,
    first_line: str = "{}",
    pid_file: Path | None = None,
    exit_code: int = 0,
) -> tuple[Path, Path]:
    pid_file = pid_file or tmp_path / f"{name}.pid"
    script = tmp_path / name
    script.write_text(
        FAKE.format(
            python=sys.executable,
            pidfile=str(pid_file),
            hold=hold,
            linger=linger,
            first_line=first_line,
            exit_code=exit_code,
        ),
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script, pid_file


def _ps(pid: int, field: str) -> str:
    return subprocess.run(
        ["ps", "-o", f"{field}=", "-p", str(pid)], capture_output=True, text=True, check=False
    ).stdout.strip()


def _ours_alive(pid: int, marker: Path) -> bool:
    """Alive, not a zombie, and its command line names this test's own tmp path."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return str(marker) in _ps(pid, "command") and not _ps(pid, "stat").startswith("Z")


def _assert_gone(pid_file: Path, marker: Path) -> None:
    deadline = time.monotonic() + 10
    while not pid_file.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    pid = int(pid_file.read_text())
    try:
        deadline = time.monotonic() + 3
        while _ours_alive(pid, marker) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert not _ours_alive(pid, marker), f"grandchild {pid} in the runner's group outlived it"
    finally:
        if _ours_alive(pid, marker):
            os.kill(pid, signal.SIGKILL)


@pytest.fixture
def reap_ours(tmp_path):
    """Kill, at teardown, any grandchild of this test still alive (an assertion failed early)."""
    yield
    for pid_file in tmp_path.rglob("*.pid"):
        try:
            pid = int(pid_file.read_text())
        except ValueError:
            continue
        if _ours_alive(pid, tmp_path):
            os.kill(pid, signal.SIGKILL)


# --- V2: DSH turn runner ---------------------------------------------------------------------


def test_dsh_supervised_turn_leaves_no_grandchild(tmp_path, reap_ours):
    exe, pid_file = _fake(tmp_path, "dshfake3052")
    rc, reasons = dsh._run_dsh_supervised(
        [str(exe)],
        cwd=str(tmp_path),
        env=dict(os.environ),
        log_path=tmp_path / "log",
        watchdog=None,
    )
    assert (rc, reasons) == (0, [])
    _assert_gone(pid_file, tmp_path)


@pytest.mark.parametrize("hold", [False, True], ids=["detach", "hold_stdout"])
def test_dsh_supervised_turn_keeps_a_nonzero_dsh_exit_code(tmp_path, reap_ours, hold):
    # DSH is reaped by the runner only after its group is killed: its own exit code is kept
    # (a check that reaped it early would lose the status and report 0).
    exe, pid_file = _fake(tmp_path, "dshfail3052", hold=hold, exit_code=3)
    rc, reasons = dsh._run_dsh_supervised(
        [str(exe)],
        cwd=str(tmp_path),
        env=dict(os.environ),
        log_path=tmp_path / "log",
        watchdog=None,
    )
    assert (rc, reasons) == (3, [])
    _assert_gone(pid_file, tmp_path)


def test_dsh_supervised_turn_is_not_held_by_a_grandchild_holding_its_output(tmp_path, reap_ours):
    exe, pid_file = _fake(tmp_path, "dshhold3052", hold=True, first_line="turn output")
    log = tmp_path / "log"
    started = time.monotonic()
    rc, reasons = dsh._run_dsh_supervised(
        [str(exe)], cwd=str(tmp_path), env=dict(os.environ), log_path=log, watchdog=None
    )
    assert (rc, reasons) == (0, [])
    assert time.monotonic() - started < 15  # the grandchild sleeps 60 s holding the pipe
    assert log.read_text(encoding="utf-8") == "turn output\n"
    _assert_gone(pid_file, tmp_path)


def test_dsh_supervised_turn_stops_at_the_wall_clock(tmp_path, reap_ours):
    # DSH hangs, then exits 0 on SIGTERM: the turn still fails with the wall-clock exit code.
    exe, pid_file = _fake(tmp_path, "dshhang3052", hold=True, linger=60)
    started = time.monotonic()
    rc, reasons = dsh._run_dsh_supervised(
        [str(exe)],
        cwd=str(tmp_path),
        env=dict(os.environ),
        log_path=tmp_path / "log",
        watchdog=None,
        wall_clock_seconds=1.0,
    )
    assert (rc, reasons) == (124, [])
    assert time.monotonic() - started < 15
    _assert_gone(pid_file, tmp_path)


def test_dsh_phase_turn_past_the_wall_clock_is_a_failed_turn(tmp_path, monkeypatch, reap_ours):
    repo = tmp_path / "repo"
    repo.mkdir()
    for cmd in (
        ["init", "-q"],
        ["config", "user.email", "t@example.invalid"],
        ["config", "user.name", "t"],
    ):
        subprocess.run(["git", *cmd], cwd=repo, check=True, capture_output=True)
    (repo / "mod.py").write_text("value = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=repo, check=True)
    session = '{"type": "session", "sessionId": "sess-wall", "cwd": "."}'
    exe, pid_file = _fake(tmp_path, "dshturn3052", linger=60, first_line=session)
    monkeypatch.setattr(dsh, "DSH_TURN_WALL_CLOCK_SECONDS", 1.0)
    monkeypatch.setattr(dsh, "find_dirty_sibling", lambda *a, **k: None)
    monkeypatch.setattr(dsh, "git_metadata_contract", lambda *a, **k: {"ok": True})
    monkeypatch.setattr(
        dsh,
        "run_issue_preflight",
        lambda subject, **k: {
            **subject,
            "decision": "ALLOW_RESUME",
            "generated_at": "2026-11-01T00:00:00Z",
        },
    )
    args = argparse.Namespace(
        issue=3052,
        goal_objective=None,
        patch=[],
        dsh_bin=str(exe),
        profile="p",
        doctor_bin="doctor",
        no_progress_steps=0,
        no_progress_compactions=0,
    )
    code, out = dsh._run_phase_turn(
        args,
        tmp_path / "state",
        repository="James3014/Nexus-new",
        repo_root=repo,
        dsh_home=tmp_path / "home",
        phase="repair",
        contract_text="CONTRACT",
        prior=[],
        parent=None,
        green_gate_command=None,
    )
    assert code == 124, out
    assert out["dsh_exit_code"] == 124
    assert out["turn_state"] != dsh.TURN_OK
    _assert_gone(pid_file, tmp_path)


# --- V3: DSH red/green gates run candidate tests -----------------------------------------------


def _candidate_repo(tmp_path: Path, pid_file: Path, hold: bool) -> Path:
    """A candidate-authored RED test that starts a background grandchild, then fails."""
    helper, _ = _fake(tmp_path, "gc_helper", hold=hold, pid_file=pid_file)
    repo = tmp_path / "candidate"
    (repo / "tests").mkdir(parents=True)
    # capfd.disabled() restores the gate's real stdout pipe, so 'hold' really holds it.
    (repo / "tests" / "test_leak.py").write_text(
        "import subprocess\n\n\n"
        "def test_leak(capfd):\n"
        "    with capfd.disabled():\n"
        f"        subprocess.run([{str(helper)!r}], check=True)\n"
        '    assert False, "RED_MARKER"\n',
        encoding="utf-8",
    )
    return repo


@pytest.mark.parametrize("gate", ["red", "green"])
@pytest.mark.parametrize("hold", [False, True], ids=["detach", "hold_stdout"])
def test_v3_dsh_gate_pytest_kills_candidate_grandchild(tmp_path, reap_ours, gate, hold):
    pid_file = tmp_path / "grandchild.pid"
    repo = _candidate_repo(tmp_path, pid_file, hold)
    node = ["tests/test_leak.py::test_leak"]
    started = time.monotonic()
    if gate == "red":
        result = dsh._run_red_tests(repo, sys.executable, node, 4.0, "RED_MARKER")
    else:
        result = dsh._run_pytest(repo, sys.executable, node, 4.0)
    elapsed = time.monotonic() - started
    if hold:
        # The holder keeps the output open: the run times out (fail closed), then is killed.
        assert "TEST_RUN_TIMEOUT" in result["codes"], result
        assert elapsed >= 3.5
    else:
        assert result["exit_code"] == 1 and not result["codes"], result
    _assert_gone(pid_file, tmp_path)


def test_dsh_gates_load_argv_command_from_their_own_tree():
    # By file path: an installed ``nexus`` package elsewhere on sys.path cannot stand in.
    module = dsh._argv_command()
    assert Path(module.__file__).resolve() == REPO / "nexus" / "core" / "argv_command.py"
    assert dsh._argv_command() is module


def test_dsh_gates_without_argv_command_are_an_environment_failure(tmp_path):
    # A copy of the script in a tree that does not ship nexus/core/argv_command.py.
    ops = tmp_path / "tree" / "scripts" / "ops"
    ops.mkdir(parents=True)
    copy = ops / "nexus-dsh-workflow"
    copy.write_bytes((REPO / "scripts" / "ops" / "nexus-dsh-workflow").read_bytes())
    lonely = SourceFileLoader("nexus_dsh_workflow_no_argv_command_3052", str(copy)).load_module()
    repo = tmp_path / "candidate"
    repo.mkdir()
    node = ["tests/test_x.py::test_x"]
    assert lonely._run_red_tests(repo, sys.executable, node, 4.0, "X")["codes"] == {
        "ENVIRONMENT_FAILURE"
    }
    assert lonely._run_pytest(repo, sys.executable, node, 4.0)["codes"] == {"ENVIRONMENT_FAILURE"}


def test_dsh_gate_group_survivor_is_its_own_failure_code(tmp_path, monkeypatch):
    def survivor(*_args, **_kwargs):
        raise dsh.CandidateProcessSurvived("process group 1 keeps members it may not signal")

    monkeypatch.setattr(dsh, "_run_reaping", survivor)
    repo = tmp_path / "candidate"
    repo.mkdir()
    node = ["tests/test_x.py::test_x"]
    red = dsh._run_red_tests(repo, sys.executable, node, 4.0, "RED_MARKER")
    green = dsh._run_pytest(repo, sys.executable, node, 4.0)
    assert red["codes"] == {"TEST_PROCESS_SURVIVED"}
    assert green["codes"] == {"TEST_PROCESS_SURVIVED"}


# --- V7: CI gate steps and the repair loop's verify step ---------------------------------------


def test_ci_gate_step_leaves_no_grandchild(tmp_path, monkeypatch, reap_ours):
    from scripts.ops import ci_gate

    monkeypatch.setattr(ci_gate, "ROOT", tmp_path)
    exe, pid_file = _fake(tmp_path, "cistep3052")
    success, _out = ci_gate.run_step("probe", f'"{exe}"')
    assert success is True
    _assert_gone(pid_file, tmp_path)


def test_ci_gate_step_with_held_output_times_out_as_a_failure(tmp_path, monkeypatch, reap_ours):
    from scripts.ops import ci_gate

    monkeypatch.setattr(ci_gate, "ROOT", tmp_path)
    monkeypatch.setattr(ci_gate, "CI_GATE_STEP_TIMEOUT_SECONDS", 1)
    exe, pid_file = _fake(tmp_path, "cihold3052", hold=True)
    started = time.monotonic()
    success, err = ci_gate.run_step("probe", f'"{exe}"')
    assert success is False
    assert "probe timed out after 1s" in err
    assert time.monotonic() - started < 15
    summary = (tmp_path / ".nexus" / "reports" / "last_failure_summary.txt").read_text()
    assert f"Exit Code: {ci_gate.CI_GATE_STEP_TIMEOUT_EXIT}" in summary
    _assert_gone(pid_file, tmp_path)


def test_repair_loop_verify_step_is_bounded():
    tree = ast.parse((REPO / "scripts/ops/autonomous_repair_loop.py").read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and getattr(node.func, "id", "") == "run_reaping_process_group"
        and node.args
        and getattr(node.args[0], "id", "") == "verify_cmd"
    ]
    assert len(calls) == 1
    assert any(kw.arg == "timeout" for kw in calls[0].keywords), "verify step has no timeout"


@pytest.mark.parametrize("hang", [False, True], ids=["passes", "hangs"])
def test_repair_loop_verify_step_reaps_and_a_timeout_fails(tmp_path, monkeypatch, reap_ours, hang):
    from scripts.ops import autonomous_repair_loop as loop

    exe, pid_file = _fake(tmp_path, "civerify3052", linger=60 if hang else 0)
    # verify_cmd is [VENV_PYTHON, CI_GATE_SCRIPT, "--dry-run"]; the fake ignores its arguments.
    monkeypatch.setattr(loop, "VENV_PYTHON", exe)
    monkeypatch.setattr(loop, "REPAIR_VERIFY_TIMEOUT_SECONDS", 1)
    started = time.monotonic()
    assert loop._verify_repair() is (not hang)
    assert time.monotonic() - started < 15
    _assert_gone(pid_file, tmp_path)


def test_repair_loop_verify_deadline_reaps_a_gate_step_in_its_own_session(
    tmp_path, monkeypatch, reap_ours
):
    # Killing the gate's group at the outer timeout would not reach a step, which runs in its
    # own session: the gate is given a deadline so the step times out and is reaped inside it.
    from scripts.ops import autonomous_repair_loop as loop
    from scripts.ops import ci_gate

    assert loop.CI_GATE_DEADLINE_ENV == ci_gate.CI_GATE_DEADLINE_ENV
    step, pid_file = _fake(tmp_path, "cinested3052", linger=60)
    gate = tmp_path / "gate_probe.py"
    gate.write_text(
        "import sys\n"
        "from pathlib import Path\n"
        f"sys.path.insert(0, {str(REPO)!r})\n"
        "from scripts.ops import ci_gate\n"
        f"ci_gate.ROOT = Path({str(tmp_path)!r})\n"
        f"ok, _ = ci_gate.run_step('probe', {repr(chr(34) + str(step) + chr(34))})\n"
        "sys.exit(0 if ok else 1)\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(loop, "VENV_PYTHON", sys.executable)
    monkeypatch.setattr(loop, "CI_GATE_SCRIPT", gate)
    monkeypatch.setattr(loop, "REPAIR_VERIFY_TIMEOUT_SECONDS", 30)
    monkeypatch.setattr(loop, "REPAIR_VERIFY_STEP_MARGIN_SECONDS", 22)
    started = time.monotonic()
    assert loop._verify_repair() is False
    # The step stopped at the gate's deadline, before the outer timeout.
    assert time.monotonic() - started < 25
    summary = (tmp_path / ".nexus" / "reports" / "last_failure_summary.txt").read_text()
    assert f"Exit Code: {ci_gate.CI_GATE_STEP_TIMEOUT_EXIT}" in summary
    _assert_gone(pid_file, tmp_path)
