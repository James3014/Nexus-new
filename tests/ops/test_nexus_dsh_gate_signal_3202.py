"""#3202 follow-up: a stop signal while ``nexus-dsh-workflow`` runs a red or green gate.

#3205 guarded the DSH turn. The start-phase chain then runs its in-process gate, which runs
candidate tests in their own session (``_run_reaping``); with Python's default SIGTERM/SIGHUP
action the workflow ended there and the candidate group kept running in the repository, and
the chain recorded nothing. The same held for the standalone ``red-gate``/``green-gate``
commands. The gate now runs under the same guard: the group is killed, the gate and chain
record the signal, and the exit code is ``128 + signal``.

Also pins three guard details: the disarm at the top of the supervisor's ``finally``, the
guard off the main thread, and ``arm()`` arming before it checks for a held signal.

Signals go only to a driver process this test starts; at teardown only processes whose command
line names this test's ``tmp_path`` are killed.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "nexus-dsh-workflow"

dsh = SourceFileLoader("nexus_dsh_workflow_gate_signal_3202", str(SCRIPT)).load_module()

# Stands in for the repository's python: the gate runs candidate tests with it. Leaves a
# grandchild in its process group that appends to the repository every 50 ms, records both
# pids, marks itself ready, then sleeps.
FAKE_PYTHON = r"""#!{python}
import os, time
TMP = {tmp!r}
if os.fork() == 0:
    null = os.open(os.devnull, os.O_RDWR)
    for fd in (0, 1, 2):
        os.dup2(null, fd)
    with open(os.path.join(TMP, "gc.pid.tmp"), "w") as fh:
        fh.write(str(os.getpid()))
    os.replace(os.path.join(TMP, "gc.pid.tmp"), os.path.join(TMP, "gc.pid"))
    for i in range(600):
        with open(os.path.join({repo!r}, "mod.py"), "a") as fh:
            fh.write("w = %d\n" % i)
        time.sleep(0.05)
    os._exit(0)
with open(os.path.join(TMP, "leader.pid.tmp"), "w") as fh:
    fh.write(str(os.getpid()))
os.replace(os.path.join(TMP, "leader.pid.tmp"), os.path.join(TMP, "leader.pid"))
while not os.path.exists(os.path.join(TMP, "gc.pid")):
    time.sleep(0.01)
with open(os.path.join(TMP, "ready"), "w") as fh:
    fh.write("1")
time.sleep(30)
"""

# start-phase with --green-contract (the DSH turn stubbed as a clean success that changed
# mod.py), or the standalone green-gate command, under a terminal's default dispositions.
DRIVER = r"""
import json, os, signal, subprocess, sys
from importlib.machinery import SourceFileLoader
for sig in (signal.SIGTERM, signal.SIGHUP):
    signal.signal(sig, signal.SIG_DFL)
signal.signal(signal.SIGINT, signal.default_int_handler)
dsh = SourceFileLoader("nexus_dsh_workflow_gate_3202_driver", {script!r}).load_module()
repo = {repo!r}
if {mode!r} == "chain":
    def ok_turn(args, root, **kw):
        with open(os.path.join(repo, "mod.py"), "a") as fh:
            fh.write("value = 2\n")
        return 0, {{"schema": dsh.PHASE_RUN_SCHEMA, "session_id": "sess-gate-3202",
                    "phase": kw["phase"], "dsh_exit_code": 0, "turn_state": dsh.TURN_OK}}
    dsh._run_phase_turn = ok_turn
    argv = ["start-phase", "--repository", "James3014/Nexus-new", "--issue", "3202",
            "--phase", "green", "--repo-root", repo, "--dsh-home", {home!r},
            "--phase-contract", {contract!r}, "--state-root", {state!r},
            "--green-contract", {green!r}, "--auto-repair", "1"]
else:
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True,
                          text=True, check=True).stdout.strip()
    with open(os.path.join(repo, "mod.py"), "a") as fh:
        fh.write("value = 2\n")
    argv = ["green-gate", "--repo-root", repo, "--base-revision", head,
            "--contract", {green!r}, "--python", {python!r}]
sys.exit(dsh.main(argv))
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


def _green_contract(path: Path) -> Path:
    path.write_text(
        json.dumps({
            "schema": dsh.GREEN_CONTRACT_SCHEMA,
            "repository": "James3014/Nexus-new",
            "issue_number": 3202,
            "target_test_nodes": ["test_mod.py::test_value"],
            "regression_pytest_targets": [],
            "allowed_change_globs": ["mod.py"],
            "lint": {"ruff_check_paths_from_changes": False, "ruff_format_preview": False},
        }),
        "utf-8",
    )
    return path


def _command(pid: int) -> str:
    """The full command line of *pid*: /proc where there is one (Linux), else ``ps -ww``."""
    try:
        return Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode()
    except OSError:
        return subprocess.run(
            ["ps", "-ww", "-o", "command=", "-p", str(pid)],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()


def _ours_alive(pid: int, marker: Path) -> bool:
    """Alive, not a zombie, and its command line names this test's own tmp path."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    stat = subprocess.run(
        ["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True, check=False
    ).stdout.strip()
    return str(marker) in _command(pid) and not stat.startswith("Z")


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


def _signal_the_gate(tmp_path: Path, driver_cleanup, mode: str, signame: str):
    repo = _git_repo(tmp_path)
    fake = tmp_path / "fakepython3202"
    fake.write_text(FAKE_PYTHON.format(python=sys.executable, tmp=str(tmp_path), repo=str(repo)))
    fake.chmod(0o755)
    (repo / ".venv" / "bin").mkdir(parents=True)
    os.symlink(fake, repo / ".venv" / "bin" / "python")
    with open(repo / ".git" / "info" / "exclude", "a", encoding="utf-8") as fh:
        fh.write(".venv/\n")
    contract = tmp_path / "contract.md"
    contract.write_text("CONTRACT allowed: mod.py\n", "utf-8")
    state = tmp_path / "state"
    driver = tmp_path / "driver3202gate.py"
    driver.write_text(
        DRIVER.format(
            script=str(SCRIPT),
            mode=mode,
            repo=str(repo),
            home=str(tmp_path / "home"),
            contract=str(contract),
            state=str(state),
            green=str(_green_contract(tmp_path / "green.json")),
            python=str(fake),
        ),
        "utf-8",
    )
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    proc = subprocess.Popen(
        [sys.executable, str(driver)],
        cwd=foreign,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, "NEXUS_DSH_SKIP_MODEL_CATALOG_CHECK": "1"},
        text=True,
    )
    driver_cleanup.append(proc)
    assert _wait_for(lambda: (tmp_path / "ready").exists(), 30), "the gate never ran the fake"
    leader = int((tmp_path / "leader.pid").read_text())
    grandchild = int((tmp_path / "gc.pid").read_text())
    assert _ours_alive(grandchild, tmp_path), (grandchild, _command(grandchild))

    signum = int(getattr(signal, signame))
    proc.send_signal(signum)
    stdout, stderr = proc.communicate(timeout=30)

    # The candidate group is gone: nothing keeps writing to the repository.
    assert _wait_for(lambda: not _ours_alive(grandchild, tmp_path), 3)
    assert not _ours_alive(leader, tmp_path)
    size = (repo / "mod.py").stat().st_size
    time.sleep(0.3)
    assert (repo / "mod.py").stat().st_size == size
    assert proc.returncode == 128 + signum, (proc.returncode, stdout, stderr)
    return json.loads(stdout.strip().splitlines()[-1]), state


@pytest.mark.parametrize("signame", ["SIGTERM", "SIGHUP", "SIGINT"])
def test_stop_signal_during_the_chain_gate_kills_its_group_and_stops_the_chain(
    tmp_path: Path, driver_cleanup, signame: str
) -> None:
    out, state = _signal_the_gate(tmp_path, driver_cleanup, "chain", signame)
    assert out["stop_reason"] == dsh.DSH_GATE_INTERRUPTED, out
    assert out["interrupted_by_signal"] == signame
    assert [p["phase"] for p in out["phases"]] == ["green"]  # no repair turn after it
    gate = out["phases"][-1]["gate"]
    assert gate["interrupted_by_signal"] == signame
    assert gate["reason_codes"] == [dsh.DSH_GATE_INTERRUPTED]
    assert gate["receipt_path"] is None
    on_disk = json.loads(Path(out["summary_path"]).read_text("utf-8"))
    assert on_disk["stop_reason"] == dsh.DSH_GATE_INTERRUPTED
    assert str(state) in out["summary_path"]


@pytest.mark.parametrize("signame", ["SIGTERM", "SIGHUP"])
def test_stop_signal_during_the_green_gate_command_kills_its_group(
    tmp_path: Path, driver_cleanup, signame: str
) -> None:
    out, _state = _signal_the_gate(tmp_path, driver_cleanup, "command", signame)
    assert out["reason_codes"] == [dsh.DSH_GATE_INTERRUPTED], out
    assert out["interrupted_by_signal"] == signame


def _chain_with_stub_gate(tmp_path: Path, monkeypatch, capsys, gate, persist, kind="green"):
    """start-phase --green-contract (or, for ``kind="red"``, --red-contract) with the turn, the
    gate and its persistence stubbed."""
    repo = _git_repo(tmp_path)
    contract = tmp_path / "contract.md"
    contract.write_text("CONTRACT allowed: mod.py\n", "utf-8")
    if kind == "green":
        chain_args = ["--green-contract", str(_green_contract(tmp_path / "green.json"))]
        chain_args += ["--auto-repair", "2"]
    else:
        red = tmp_path / "red.json"
        red.write_text(
            json.dumps({
                "schema": dsh.RED_CONTRACT_SCHEMA,
                "repository": "James3014/Nexus-new",
                "issue_number": 3202,
                "invariant": "value must be three",
                "test_nodes": ["test_red.py::test_value_is_three"],
                "expected_failure": {"kind": "assertion", "message_regex": "assert 1 == 3"},
                "forbidden_oracle_literals": [],
                "test_path_globs": ["test_red.py"],
            }),
            "utf-8",
        )
        chain_args = ["--red-contract", str(red), "--auto-repair-red", "2"]
    turns: list[str] = []

    def ok_turn(args, root, **kwargs):
        turns.append(kwargs["phase"])
        return 0, {
            "schema": dsh.PHASE_RUN_SCHEMA,
            "session_id": f"sess-gate-3202-{len(turns)}",
            "phase": kwargs["phase"],
            "dsh_exit_code": 0,
            "turn_state": dsh.TURN_OK,
        }

    monkeypatch.setattr(dsh, "_run_phase_turn", ok_turn)
    monkeypatch.setattr(dsh, f"run_{kind}_gate", gate)
    monkeypatch.setattr(dsh, f"persist_{kind}_gate_with_sidecar", persist)
    before = {sig: signal.getsignal(sig) for sig in dsh.DSH_TURN_STOP_SIGNALS}
    code = dsh.main([
        "start-phase",
        "--repository",
        "James3014/Nexus-new",
        "--issue",
        "3202",
        "--phase",
        kind,
        "--repo-root",
        str(repo),
        "--dsh-home",
        str(tmp_path / "home"),
        "--phase-contract",
        str(contract),
        "--state-root",
        str(tmp_path / "state"),
        *chain_args,
    ])
    assert {sig: signal.getsignal(sig) for sig in dsh.DSH_TURN_STOP_SIGNALS} == before
    return code, json.loads(capsys.readouterr().out.strip().splitlines()[-1]), turns


def _deliver(signum: int) -> None:
    """What the interpreter does when *signum* arrives: call its handler (nothing is sent)."""
    handler = signal.getsignal(signum)
    assert callable(handler), handler  # the gate runs under the guard's handler
    handler(signum, None)


@pytest.mark.parametrize("kind", ["green", "red"])
def test_stop_signal_while_the_chain_gate_runs_is_raised_and_recorded(
    tmp_path: Path, monkeypatch, capsys, kind: str
) -> None:
    persisted: list[str] = []

    def gate_hit_by_a_signal(**_kwargs):
        _deliver(signal.SIGTERM)
        raise AssertionError("not reached: the armed guard raises")

    code, out, turns = _chain_with_stub_gate(
        tmp_path,
        monkeypatch,
        capsys,
        gate_hit_by_a_signal,
        lambda *a, **k: persisted.append("x") or tmp_path / "r.json",
        kind,
    )
    assert code == 128 + signal.SIGTERM
    assert out["stop_reason"] == dsh.DSH_GATE_INTERRUPTED
    assert out["interrupted_by_signal"] == "SIGTERM"
    gate = out["phases"][-1]["gate"]
    assert gate["kind"] == kind
    assert gate["reason_codes"] == [dsh.DSH_GATE_INTERRUPTED]
    assert gate["interrupted_by_signal"] == "SIGTERM"
    assert turns == [kind] and persisted == []  # no repair turn after it


def test_stop_signal_while_the_gate_receipt_is_persisted_is_held_then_stops_the_chain(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    persisted: list[str] = []
    receipt_path = tmp_path / "green-receipt.json"

    def failing_gate(**_kwargs):
        # REVISE_GREEN would start a repair turn; the held signal must stop the chain first.
        return {
            "decision": "REVISE_GREEN",
            "reason_codes": ["TARGET_FAILED"],
            "receipt_hash": "sha256:" + "0" * 64,
            "contract_hash": "sha256:" + "1" * 64,
        }

    def persist_hit_by_a_signal(*_args, **_kwargs):
        _deliver(signal.SIGHUP)  # not armed while persisting: held, the write completes
        persisted.append("done")
        return receipt_path

    code, out, turns = _chain_with_stub_gate(
        tmp_path, monkeypatch, capsys, failing_gate, persist_hit_by_a_signal
    )
    assert persisted == ["done"]
    assert code == 128 + signal.SIGHUP
    assert out["stop_reason"] == dsh.DSH_GATE_INTERRUPTED
    gate = out["phases"][-1]["gate"]
    assert gate["receipt_path"] == str(receipt_path)
    assert gate["interrupted_by_signal"] == "SIGHUP"
    assert turns == ["green"]  # no repair turn


def test_signal_in_cleanup_after_a_non_signal_error_is_held_until_cleanup_is_done(
    tmp_path: Path, monkeypatch
) -> None:
    # The watchdog raises (a non-signal error) while DSH is supervised, so the group cleanup
    # runs from ``finally``. A stop signal landing during that cleanup (the handler is called
    # directly: nothing is sent) must not cut it short.
    exe = tmp_path / "dshslow3202"
    exe.write_text(
        f"#!{sys.executable}\nimport time\nprint('line', flush=True)\ntime.sleep(2)\n", "utf-8"
    )
    exe.chmod(0o755)

    class Broken:
        def feed_line(self, _line: str) -> list[str]:
            raise RuntimeError("watchdog failed")

    real_cleanup = dsh._kill_dsh_group_and_reap
    signals = dsh._TurnSignals()
    finished: list[int] = []

    def cleanup_hit_by_a_signal(proc, failures):
        signals._handle(signal.SIGTERM, None)
        real_cleanup(proc, failures)
        finished.append(proc.pid)

    monkeypatch.setattr(dsh, "_kill_dsh_group_and_reap", cleanup_hit_by_a_signal)
    with signals:
        with pytest.raises(RuntimeError, match="watchdog failed"):
            dsh._run_dsh_supervised(
                [str(exe)],
                cwd=str(tmp_path),
                env=dict(os.environ),
                log_path=tmp_path / "log",
                watchdog=Broken(),
                cleanup_failures=[],
                signals=signals,
            )
    assert len(finished) == 1  # the cleanup ran to the end
    assert signals.received == signal.SIGTERM  # held, not raised out of the cleanup


def test_turn_signals_off_the_main_thread_install_nothing_and_do_not_fail() -> None:
    before = {sig: signal.getsignal(sig) for sig in dsh.DSH_TURN_STOP_SIGNALS}
    seen: dict[str, object] = {}

    def body() -> None:
        try:
            with dsh._TurnSignals() as signals:
                seen["prior"] = dict(signals._prior)
                seen["during"] = {sig: signal.getsignal(sig) for sig in dsh.DSH_TURN_STOP_SIGNALS}
                signals.arm()
                signals.disarm()
        except BaseException as exc:  # noqa: BLE001 - reported to the main thread
            seen["error"] = exc

    thread = threading.Thread(target=body)
    thread.start()
    thread.join(10)
    assert "error" not in seen, seen.get("error")
    assert seen["prior"] == {}
    assert seen["during"] == before
    assert {sig: signal.getsignal(sig) for sig in dsh.DSH_TURN_STOP_SIGNALS} == before


def test_arm_raises_a_signal_that_lands_right_after_the_held_check() -> None:
    # A signal whose handler runs just after arm() found nothing held must still be raised:
    # either the guard is already armed (the handler raises) or arm() raises it.
    previous = {sig: signal.getsignal(sig) for sig in dsh.DSH_TURN_STOP_SIGNALS}
    with dsh._TurnSignals() as signals:
        real_raise_held = signals.raise_held

        def raise_held_then_a_signal() -> None:
            real_raise_held()
            signals._handle(signal.SIGTERM, None)

        signals.raise_held = raise_held_then_a_signal
        with pytest.raises(dsh.DshTurnInterrupted) as raised:
            signals.arm()
        assert raised.value.signum == signal.SIGTERM
        assert not signals._armed  # raised once, then disarmed
        signals._handle(signal.SIGHUP, None)  # a later signal is not raised
    assert {sig: signal.getsignal(sig) for sig in dsh.DSH_TURN_STOP_SIGNALS} == previous
