"""#3202: a SIGTERM, SIGHUP or SIGINT to ``nexus-dsh-workflow`` during a DSH turn.

Python's default SIGTERM/SIGHUP action ended the workflow without running ``finally``: DSH's
process group (its own session) kept running and writing to the repository, and the turn was
never recorded. The workflow now kills and confirms the group, records the turn as interrupted
and returns ``128 + signal``.

The workflow runs in a child python process of this test (a driver script in ``tmp_path``) with
a fake DSH whose background grandchild keeps writing to the test repository. Signals go only to
that driver; at teardown only processes whose command line names this test's ``tmp_path`` are
killed.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "nexus-dsh-workflow"

guard = SourceFileLoader("nexus_dsh_workflow_signal_3202", str(SCRIPT)).load_module()

# Prints its session, leaves a grandchild in its process group that appends to the repository
# every 50 ms, records both pids, prints "ready", then sleeps.
FAKE_DSH = r"""#!{python}
import json, os, sys, time
TMP = {tmp!r}
print(json.dumps({{"type": "session", "sessionId": "sess-3202", "cwd": os.getcwd()}}), flush=True)
if os.fork() == 0:
    null = os.open(os.devnull, os.O_RDWR)
    for fd in (0, 1, 2):
        os.dup2(null, fd)
    with open(os.path.join(TMP, "gc.pid.tmp"), "w") as fh:
        fh.write(str(os.getpid()))
    os.replace(os.path.join(TMP, "gc.pid.tmp"), os.path.join(TMP, "gc.pid"))
    for i in range(600):
        with open("mod.py", "a") as fh:
            fh.write("w = %d\n" % i)
        time.sleep(0.05)
    os._exit(0)
with open(os.path.join(TMP, "leader.pid.tmp"), "w") as fh:
    fh.write(str(os.getpid()))
os.replace(os.path.join(TMP, "leader.pid.tmp"), os.path.join(TMP, "leader.pid"))
while not os.path.exists(os.path.join(TMP, "gc.pid")):
    time.sleep(0.01)
print("ready", flush=True)
time.sleep(30)
"""

# Runs one start-phase turn the way the command does, with the preflight stubbed, under the
# default dispositions a terminal session has.
DRIVER = r"""
import argparse, json, signal, sys
from importlib.machinery import SourceFileLoader
from pathlib import Path
for sig in (signal.SIGTERM, signal.SIGHUP):
    signal.signal(sig, signal.SIG_DFL)
signal.signal(signal.SIGINT, signal.default_int_handler)
dsh = SourceFileLoader("nexus_dsh_workflow_3202_driver", {script!r}).load_module()
dsh.find_dirty_sibling = lambda *a, **k: None
dsh.git_metadata_contract = lambda *a, **k: {{"ok": True}}
dsh.run_issue_preflight = lambda subject, **k: {{
    **subject, "decision": "ALLOW_RESUME", "generated_at": "2026-11-02T00:00:00Z"
}}
args = argparse.Namespace(
    issue=3202, goal_objective=None, patch=[], dsh_bin={dsh_bin!r}, profile="p",
    doctor_bin="doctor", no_progress_steps=0, no_progress_compactions=0,
)
code, out = dsh._run_phase_turn(
    args, Path({state!r}), repository="James3014/Nexus-new", repo_root=Path({repo!r}),
    dsh_home=Path({home!r}), phase="repair", contract_text="CONTRACT", prior=[], parent=None,
    green_gate_command=None,
)
print(json.dumps(out, sort_keys=True))
sys.exit(code)
"""


def _git_repo(base: Path) -> Path:
    repo = base / "repo"
    repo.mkdir()
    for cmd in (
        ["init", "-q"],
        ["config", "user.email", "t@example.invalid"],
        ["config", "user.name", "t"],
    ):
        subprocess.run(["git", *cmd], cwd=repo, check=True, capture_output=True)
    (repo / "mod.py").write_text("value = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=repo, check=True)
    return repo


def _ps(pid: int, field: str) -> str:
    # -ww: unlimited width. Without it procps (Linux) cuts the line at 80 columns when it has
    # no terminal (under pytest, COLUMNS unset or not), and the interpreter path plus this
    # test's tmp path is longer than that: the tmp path was cut off, so no process matched.
    return subprocess.run(
        ["ps", "-ww", "-o", f"{field}=", "-p", str(pid)],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()


def _command(pid: int) -> str:
    """The full command line of *pid*: /proc where there is one (Linux), else ``ps``."""
    try:
        return Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode()
    except OSError:
        return _ps(pid, "command")


def _ours_alive(pid: int, marker: Path) -> bool:
    """Alive, not a zombie, and its command line names this test's own tmp path."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return str(marker) in _command(pid) and not _ps(pid, "stat").startswith("Z")


def _wait_for(predicate, seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


@pytest.fixture
def driver_cleanup(tmp_path):
    """Kill, at teardown, the driver and any of this test's fake processes still alive."""
    started: list[subprocess.Popen] = []
    yield started
    for proc in started:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
    for name in ("gc.pid", "leader.pid"):
        path = tmp_path / name
        if path.exists():
            pid = int(path.read_text())
            if _ours_alive(pid, tmp_path):
                os.kill(pid, signal.SIGKILL)


@pytest.mark.parametrize("signame", ["SIGTERM", "SIGHUP", "SIGINT"])
def test_stop_signal_kills_the_dsh_group_and_records_an_interrupted_turn(
    tmp_path: Path, driver_cleanup, signame: str
) -> None:
    signum = int(getattr(signal, signame))
    repo = _git_repo(tmp_path)
    dsh_bin = tmp_path / "dshfake3202"
    dsh_bin.write_text(FAKE_DSH.format(python=sys.executable, tmp=str(tmp_path)), "utf-8")
    dsh_bin.chmod(0o755)
    state = tmp_path / "state"
    driver = tmp_path / "driver3202.py"
    driver.write_text(
        DRIVER.format(
            script=str(SCRIPT),
            dsh_bin=str(dsh_bin),
            state=str(state),
            repo=str(repo),
            home=str(tmp_path / "home"),
        ),
        "utf-8",
    )
    env = {**os.environ, "NEXUS_DSH_SKIP_MODEL_CATALOG_CHECK": "1"}
    proc = subprocess.Popen(
        [sys.executable, str(driver)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        text=True,
    )
    driver_cleanup.append(proc)

    def ready() -> bool:
        logs = list((state / "phases" / "3202").glob("*.log"))
        return bool(logs) and "ready" in logs[0].read_text("utf-8", "replace")

    assert _wait_for(ready, 20), "fake DSH never reported ready"
    leader = int((tmp_path / "leader.pid").read_text())
    grandchild = int((tmp_path / "gc.pid").read_text())
    assert _ours_alive(grandchild, tmp_path), (
        grandchild,
        _command(grandchild),
        _ps(grandchild, "stat"),
    )

    proc.send_signal(signum)
    stdout, stderr = proc.communicate(timeout=30)

    # The whole DSH group is gone: nothing keeps writing to the repository.
    assert _wait_for(lambda: not _ours_alive(grandchild, tmp_path), 3)
    assert not _ours_alive(leader, tmp_path)
    size = (repo / "mod.py").stat().st_size
    time.sleep(0.3)
    assert (repo / "mod.py").stat().st_size == size

    # The workflow ended on its own, with 128 + signal and an interrupted turn recorded.
    assert proc.returncode == 128 + signum, (proc.returncode, stdout, stderr)
    out = json.loads(stdout.strip().splitlines()[-1])
    assert out["decision"] == "INTERRUPTED"
    assert out["reason_codes"] == [guard.DSH_TURN_INTERRUPTED]
    assert out["interrupted_by_signal"] == signame
    assert out["dsh_exit_code"] == 128 + signum
    assert out["session_id"] == "sess-3202"
    assert "cleanup_reason_codes" not in out
    assert guard._turn_stop_reason(proc.returncode, out) == guard.DSH_TURN_INTERRUPTED
    turn = guard.load_turn_state(state, "sess-3202")
    assert turn is not None
    assert turn["state"] in (guard.TURN_FAILED_DIRTY, guard.TURN_FAILED_CLEAN)
    assert turn["dsh_exit_code"] == 128 + signum
    assert turn["interrupted_by_signal"] == signame
    receipt = json.loads(Path(turn["quarantine_receipt"]).read_text("utf-8"))
    assert receipt["interrupted_by_signal"] == signame


def test_turn_signals_hold_a_signal_until_armed_and_raise_it_once() -> None:
    previous = {sig: signal.getsignal(sig) for sig in guard.DSH_TURN_STOP_SIGNALS}
    with guard._TurnSignals() as signals:
        # Called directly: no signal is sent. Not armed (DSH spawning, cleanup, recording):
        # remembered, not raised.
        signals._handle(signal.SIGTERM, None)
        signals._handle(signal.SIGHUP, None)
        assert signals.received == signal.SIGTERM
        with pytest.raises(guard.DshTurnInterrupted) as raised:
            signals.arm()
        assert raised.value.signum == signal.SIGTERM
        signals.arm()  # already raised: not raised again, and not armed again
        signals._handle(signal.SIGTERM, None)
    assert {sig: signal.getsignal(sig) for sig in guard.DSH_TURN_STOP_SIGNALS} == previous


def test_turn_signals_raise_while_armed_and_leave_an_ignored_signal_ignored() -> None:
    hup_before = signal.getsignal(signal.SIGHUP)
    signal.signal(signal.SIGHUP, signal.SIG_IGN)
    try:
        with guard._TurnSignals() as signals:
            assert signal.getsignal(signal.SIGHUP) == signal.SIG_IGN  # nohup stays honoured
            assert signal.getsignal(signal.SIGTERM) == signals._handle
            signals.arm()
            with pytest.raises(guard.DshTurnInterrupted):
                signals._handle(signal.SIGTERM, None)
            signals._handle(signal.SIGTERM, None)  # a second signal is ignored
        assert signal.getsignal(signal.SIGHUP) == signal.SIG_IGN
    finally:
        signal.signal(signal.SIGHUP, hup_before)


def test_stop_signal_during_the_group_cleanup_is_held_until_the_cleanup_is_done(
    tmp_path: Path, monkeypatch
) -> None:
    # A stop signal landing while the group is killed and DSH reaped (the handler is called
    # directly: no signal is sent) must not cut that cleanup short.
    exe = tmp_path / "dshquick3202"
    exe.write_text(f"#!{sys.executable}\nprint('done', flush=True)\n", "utf-8")
    exe.chmod(0o755)
    real_cleanup = guard._kill_dsh_group_and_reap
    signals = guard._TurnSignals()
    finished: list[int] = []

    def cleanup_hit_by_a_signal(proc, failures):
        signals._handle(signal.SIGTERM, None)
        real_cleanup(proc, failures)
        finished.append(proc.pid)

    monkeypatch.setattr(guard, "_kill_dsh_group_and_reap", cleanup_hit_by_a_signal)
    failures: list[str] = []
    with signals:
        code, reasons = guard._run_dsh_supervised(
            [str(exe)],
            cwd=str(tmp_path),
            env=dict(os.environ),
            log_path=tmp_path / "log",
            watchdog=None,
            cleanup_failures=failures,
            signals=signals,
        )
    assert (code, reasons, failures) == (0, [], [])
    assert len(finished) == 1  # the cleanup ran to the end, once
    assert signals.received == signal.SIGTERM  # held for the caller to record


def _green_contract(path: Path, issue: int) -> Path:
    path.write_text(
        json.dumps({
            "schema": guard.GREEN_CONTRACT_SCHEMA,
            "repository": "James3014/Nexus-new",
            "issue_number": issue,
            "target_test_nodes": ["test_mod.py::test_value"],
            "regression_pytest_targets": [],
            "allowed_change_globs": ["mod.py"],
            "lint": {"ruff_check_paths_from_changes": False, "ruff_format_preview": False},
        }),
        "utf-8",
    )
    return path


def test_interrupted_chained_turn_exits_128_plus_signal(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    repo = _git_repo(tmp_path)
    contract = tmp_path / "contract.md"
    contract.write_text("CONTRACT allowed: mod.py\n", "utf-8")
    green = _green_contract(tmp_path / "green.json", 3202)
    turns: list[str] = []

    def interrupted_turn(args, root, **kwargs):
        turns.append(kwargs["phase"])
        return 130, {
            "schema": guard.PHASE_RUN_SCHEMA,
            "session_id": "sess-3202-chain",
            "phase": kwargs["phase"],
            "dsh_exit_code": 130,
            "turn_state": guard.TURN_FAILED_CLEAN,
            "decision": "INTERRUPTED",
            "reason_codes": [guard.DSH_TURN_INTERRUPTED],
            "interrupted_by_signal": "SIGINT",
        }

    monkeypatch.setattr(guard, "_run_phase_turn", interrupted_turn)
    code = guard.main([
        "start-phase",
        "--repository",
        "James3014/Nexus-new",
        "--issue",
        "3202",
        "--phase",
        "green",
        "--repo-root",
        str(repo),
        "--dsh-home",
        str(tmp_path / "home"),
        "--phase-contract",
        str(contract),
        "--state-root",
        str(tmp_path / "state"),
        "--green-contract",
        str(green),
        "--auto-repair",
        "2",
    ])
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["stop_reason"] == guard.DSH_TURN_INTERRUPTED, out
    assert turns == ["green"]  # no gate, no repair turn after the interruption
    assert code == 130


# Runs ``resume`` the way the command does, with the binding, preflight and receipt stubbed
# (#3235). The DSH stand-in is FAKE_DSH: its group keeps writing to the repository.
RESUME_DRIVER = r"""
import signal, sys
from importlib.machinery import SourceFileLoader
from pathlib import Path
for sig in (signal.SIGTERM, signal.SIGHUP):
    signal.signal(sig, signal.SIG_DFL)
signal.signal(signal.SIGINT, signal.default_int_handler)
dsh = SourceFileLoader("nexus_dsh_workflow_3235_driver", {script!r}).load_module()
binding = {{
    "session_id": "sess-3235", "repository": "James3014/Nexus-new", "issue_number": 3235,
    "repo_root": {repo!r}, "dsh_home": {home!r}, "goal_id": None, "binding_hash": None,
}}
dsh.load_binding = lambda root, session_id: binding
dsh.git_metadata_contract = lambda repo: {{"ok": True}}
dsh.run_preflight = lambda binding, doctor_bin: {{"decision": "ALLOW_RESUME"}}
dsh.persist_preflight = lambda root, receipt: Path({state!r}) / "receipt.json"
sys.exit(dsh.main([
    "resume", "--session-id", "sess-3235", "--state-root", {state!r},
    "--dsh-bin", {dsh_bin!r}, "--task", "continue",
]))
"""


@pytest.mark.parametrize("signame", ["SIGTERM", "SIGHUP", "SIGINT"])
def test_stop_signal_during_a_resumed_turn_kills_the_dsh_group_and_records_it(
    tmp_path: Path, driver_cleanup, signame: str
) -> None:
    """#3235: ``resume`` ran DSH through plain ``subprocess.run`` with no handler, so a stop
    signal ended the workflow and left DSH's group writing; it now runs supervised."""
    signum = int(getattr(signal, signame))
    repo = _git_repo(tmp_path)
    dsh_bin = tmp_path / "dshfake3235"
    dsh_bin.write_text(FAKE_DSH.format(python=sys.executable, tmp=str(tmp_path)), "utf-8")
    dsh_bin.chmod(0o755)
    state = tmp_path / "state"
    driver = tmp_path / "driver3235.py"
    driver.write_text(
        RESUME_DRIVER.format(
            script=str(SCRIPT),
            dsh_bin=str(dsh_bin),
            state=str(state),
            repo=str(repo),
            home=str(tmp_path / "home"),
        ),
        "utf-8",
    )
    env = {**os.environ, "NEXUS_DSH_SKIP_MODEL_CATALOG_CHECK": "1"}
    proc = subprocess.Popen(
        [sys.executable, str(driver)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        text=True,
    )
    driver_cleanup.append(proc)

    def ready() -> bool:
        logs = list((state / "resumes" / "sess-3235").glob("*.log"))
        return bool(logs) and "ready" in logs[0].read_text("utf-8", "replace")

    assert _wait_for(ready, 20), "fake DSH never reported ready"
    leader = int((tmp_path / "leader.pid").read_text())
    grandchild = int((tmp_path / "gc.pid").read_text())
    assert _ours_alive(grandchild, tmp_path), (
        grandchild,
        _command(grandchild),
        _ps(grandchild, "stat"),
    )

    proc.send_signal(signum)
    stdout, stderr = proc.communicate(timeout=30)

    # The whole DSH group is gone: nothing keeps writing to the repository.
    assert _wait_for(lambda: not _ours_alive(grandchild, tmp_path), 3)
    assert not _ours_alive(leader, tmp_path)
    size = (repo / "mod.py").stat().st_size
    time.sleep(0.3)
    assert (repo / "mod.py").stat().st_size == size

    # The workflow ended on its own, with 128 + signal and an interrupted turn recorded.
    assert proc.returncode == 128 + signum, (proc.returncode, stdout, stderr)
    turn = guard.load_turn_state(state, "sess-3235")
    assert turn is not None
    assert turn["state"] in (guard.TURN_FAILED_DIRTY, guard.TURN_FAILED_CLEAN)
    assert turn["dsh_exit_code"] == 128 + signum
    assert turn["interrupted_by_signal"] == signame
    receipt = json.loads(Path(turn["quarantine_receipt"]).read_text("utf-8"))
    assert receipt["interrupted_by_signal"] == signame
    record = json.loads(stderr.strip().splitlines()[-1])
    assert record["log_path"].endswith(".log")
    assert "ready" in stdout  # DSH's output, echoed from the log once the turn is over
