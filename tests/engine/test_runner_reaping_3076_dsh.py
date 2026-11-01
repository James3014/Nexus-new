"""#3076 items 1-5: the DSH supervised turn and ci_gate.run_step after #3071.

- ``_run_dsh_supervised`` did not check SIGCHLD before spawning DSH (item 1), swallowed a
  failed group SIGKILL without confirming the group empty (item 2), signalled the group itself
  as soon as kqueue reported NOTE_EXIT, before DSH was a zombie (item 3), and returned DSH's own
  exit code with no record when a process outside the group kept the output open (item 4).
- ``ci_gate.run_step`` runs without a shell; ``$`` and backquote expansion passed on as
  literal text (item 5).

Every fake DSH records its own pid and its background grandchild's pid in this test's tmp dir;
only those pids are signalled by the tests, and only while ``ps`` shows this test's tmp path in
their command line.
"""

from __future__ import annotations

import argparse
import errno
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
    "nexus_dsh_workflow_reaping_3076", str(REPO / "scripts" / "ops" / "nexus-dsh-workflow")
).load_module()

# Records its own pid, leaves a grandchild (in its process group, or in a new session with
# ESCAPE) that keeps stdout open with HOLD and records its pid, prints FIRST_LINE once the
# grandchild is there, then sleeps LINGER seconds and exits EXIT_CODE.
FAKE = r"""#!{python}
import os, sys, time
TMP = {tmp!r}
with open(os.path.join(TMP, "leader.pid.tmp"), "w") as fh:
    fh.write(str(os.getpid()))
os.replace(os.path.join(TMP, "leader.pid.tmp"), os.path.join(TMP, "leader.pid"))
pid = os.fork()
if pid == 0:
    if {escape!r}:
        os.setsid()
    if os.fork() == 0:
        if not {hold!r}:
            null = os.open(os.devnull, os.O_RDWR)
            for fd in (0, 1, 2):
                os.dup2(null, fd)
        with open(os.path.join(TMP, "gc.pid.tmp"), "w") as fh:
            fh.write(str(os.getpid()))
        os.replace(os.path.join(TMP, "gc.pid.tmp"), os.path.join(TMP, "gc.pid"))
        time.sleep(30)
        os._exit(0)
    os._exit(0)
os.waitpid(pid, 0)
while not os.path.exists(os.path.join(TMP, "gc.pid")):
    time.sleep(0.01)
print({first_line!r}, flush=True)
time.sleep({linger!r})
sys.exit({exit_code!r})
"""


def _fake(
    tmp_path: Path,
    *,
    hold: bool = False,
    escape: bool = False,
    linger: float = 0,
    exit_code: int = 0,
    first_line: str = "{}",
) -> Path:
    script = tmp_path / "dshfake3076"
    script.write_text(
        FAKE.format(
            python=sys.executable,
            tmp=str(tmp_path),
            first_line=first_line,
            escape=escape,
            hold=hold,
            linger=linger,
            exit_code=exit_code,
        ),
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script


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


def _pid(tmp_path: Path, name: str) -> int:
    path = tmp_path / name
    deadline = time.monotonic() + 10
    while not path.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    return int(path.read_text())


def _gone(pid: int, marker: Path) -> bool:
    deadline = time.monotonic() + 3
    while _ours_alive(pid, marker) and time.monotonic() < deadline:
        time.sleep(0.05)
    return not _ours_alive(pid, marker)


def _reaped(pid: int) -> bool:
    """Whether this test process's child *pid* has been reaped (it is no longer our child)."""
    try:
        os.waitpid(pid, os.WNOHANG)
    except ChildProcessError:
        return True
    return False


@pytest.fixture
def reap_ours(tmp_path):
    """Kill, at teardown, any of this test's own fake processes still alive."""
    yield
    for name in ("gc.pid", "leader.pid"):
        path = tmp_path / name
        if not path.exists():
            continue
        pid = int(path.read_text())
        if _ours_alive(pid, tmp_path):
            os.kill(pid, signal.SIGKILL)


@pytest.fixture
def sigchld_restored():
    previous = signal.getsignal(signal.SIGCHLD)
    yield
    signal.signal(signal.SIGCHLD, previous)


def _supervised(tmp_path: Path, exe: Path, failures: list[str] | None = None, **kwargs):
    return dsh._run_dsh_supervised(
        [str(exe)],
        cwd=str(tmp_path),
        env=dict(os.environ),
        log_path=tmp_path / "log",
        watchdog=kwargs.pop("watchdog", None),
        cleanup_failures=failures,
        **kwargs,
    )


def _helper():
    return dsh._argv_command()


def _phase_turn(tmp_path: Path, monkeypatch, exe: Path):
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
        issue=3076,
        goal_objective=None,
        patch=[],
        dsh_bin=str(exe),
        profile="p",
        doctor_bin="doctor",
        no_progress_steps=0,
        no_progress_compactions=0,
    )
    return dsh._run_phase_turn(
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


# --- item 1: refuse before spawning when DSH could be reaped by someone else ------------------


@pytest.mark.parametrize("handler", ["ignore", "python_handler"])
def test_dsh_turn_is_not_started_when_sigchld_is_not_default(tmp_path, sigchld_restored, handler):
    exe = _fake(tmp_path)
    signal.signal(signal.SIGCHLD, signal.SIG_IGN if handler == "ignore" else (lambda *_: None))
    with pytest.raises(dsh.DshWorkflowError) as caught:
        _supervised(tmp_path, exe)
    assert caught.value.code == "DSH_PROCESS_GROUP_REAPING_UNAVAILABLE"
    assert "SIGCHLD" in str(caught.value)
    assert not (tmp_path / "leader.pid").exists()  # nothing was spawned
    assert not (tmp_path / "log").exists()


def test_dsh_turn_is_not_started_without_the_reaping_helper(tmp_path, monkeypatch):
    exe = _fake(tmp_path)

    def unavailable():
        raise OSError(errno.ENOENT, "argv_command.py unavailable")

    monkeypatch.setattr(dsh, "_argv_command", unavailable)
    with pytest.raises(dsh.DshWorkflowError) as caught:
        _supervised(tmp_path, exe)
    assert caught.value.code == "DSH_PROCESS_GROUP_REAPING_UNAVAILABLE"
    assert not (tmp_path / "leader.pid").exists()


def test_dsh_phase_turn_refused_before_spawning_is_a_blocked_preflight(
    tmp_path, monkeypatch, sigchld_restored
):
    exe = _fake(tmp_path)
    signal.signal(signal.SIGCHLD, signal.SIG_IGN)
    code, out = _phase_turn(tmp_path, monkeypatch, exe)
    signal.signal(signal.SIGCHLD, signal.SIG_DFL)
    assert code == dsh.EXIT_BLOCKED, out
    assert out["decision"] == "BLOCK_RESUME"
    assert out["reason_code"] == "DSH_PROCESS_GROUP_REAPING_UNAVAILABLE"
    assert out["provider_invocation_allowed"] is False
    assert Path(out["receipt_path"]).is_file()
    assert not (tmp_path / "leader.pid").exists()


# --- item 2: the group is confirmed empty; a member that survives is reported -----------------


@pytest.mark.parametrize(
    ("raised", "code"),
    [
        (PermissionError(errno.EPERM, "process group keeps members (pids [1])"), "SURVIVED"),
        (ChildProcessError("reaped elsewhere"), "REAPED_ELSEWHERE"),
    ],
    ids=["survivor", "reaped_elsewhere"],
)
def test_dsh_turn_reports_a_failed_group_cleanup(tmp_path, monkeypatch, reap_ours, raised, code):
    real = _helper().kill_group_if_exited

    def reports_failure(process):
        if not real(process):  # really kill and reap; then report what the helper found
            return False
        raise raised

    monkeypatch.setattr(_helper(), "kill_group_if_exited", reports_failure)
    exe = _fake(tmp_path)
    failures: list[str] = []
    rc, reasons = _supervised(tmp_path, exe, failures)
    expected = {"SURVIVED": "DSH_GROUP_MEMBER_SURVIVED", "REAPED_ELSEWHERE": "DSH_REAPED_ELSEWHERE"}
    assert failures == [expected[code]]
    assert (rc, reasons) == (125, [])  # DSH exited 0: the turn is still not a success
    assert _gone(_pid(tmp_path, "gc.pid"), tmp_path)
    assert _reaped(_pid(tmp_path, "leader.pid"))


def test_dsh_turn_keeps_a_nonzero_exit_code_with_a_failed_cleanup(tmp_path, monkeypatch, reap_ours):
    real = _helper().kill_group_if_exited

    def survivor(process):
        if not real(process):
            return False
        raise PermissionError(errno.EPERM, "process group keeps members (pids [1])")

    monkeypatch.setattr(_helper(), "kill_group_if_exited", survivor)
    failures: list[str] = []
    rc, reasons = _supervised(tmp_path, _fake(tmp_path, exit_code=3), failures)
    assert (rc, reasons, failures) == (3, [], ["DSH_GROUP_MEMBER_SURVIVED"])


def test_dsh_turn_cleanup_goes_through_the_confirming_helper(tmp_path, monkeypatch, reap_ours):
    # Without the helper's kill the grandchild (in DSH's group) would outlive the turn.
    real = _helper().kill_group_if_exited
    calls = []

    def recording(process):
        calls.append(process.pid)
        return real(process)

    monkeypatch.setattr(_helper(), "kill_group_if_exited", recording)
    exe = _fake(tmp_path, hold=True)
    failures: list[str] = []
    assert _supervised(tmp_path, exe, failures) == (0, [])
    assert failures == []
    assert calls and set(calls) == {_pid(tmp_path, "leader.pid")}
    assert _gone(_pid(tmp_path, "gc.pid"), tmp_path)
    assert _reaped(_pid(tmp_path, "leader.pid"))


def test_dsh_phase_turn_with_a_group_survivor_is_a_failed_dirty_turn(
    tmp_path, monkeypatch, reap_ours
):
    real = _helper().kill_group_if_exited

    def survivor(process):
        if not real(process):
            return False
        raise PermissionError(errno.EPERM, "process group keeps members (pids [1])")

    monkeypatch.setattr(_helper(), "kill_group_if_exited", survivor)
    session = '{"type": "session", "sessionId": "sess-3076", "cwd": "."}'
    code, out = _phase_turn(tmp_path, monkeypatch, _fake(tmp_path, first_line=session))
    assert code == 125, out
    assert out["dsh_exit_code"] == 125
    assert out["cleanup_reason_codes"] == ["DSH_GROUP_MEMBER_SURVIVED"]
    assert out["turn_state"] == dsh.TURN_FAILED_DIRTY  # a survivor may still write
    assert "decision" not in out  # no new decision value
    assert dsh._turn_stop_reason(code, out) == "DSH_TURN_FAILED"


# --- item 3: the group is signalled only once the helper sees DSH exited and unreaped ---------


def test_dsh_turn_waits_for_the_helper_before_signalling_an_exited_group(
    tmp_path, monkeypatch, reap_ours
):
    # As on the kqueue path (macOS, Python < 3.13): NOTE_EXIT came, but DSH is still exiting, not
    # yet a zombie, so the helper does not yet report it exited. The turn must not signal the
    # group itself meanwhile; it retries the helper until DSH can be killed and reaped.
    real = _helper().kill_group_if_exited
    calls = []
    signals = []

    def still_exiting(process):
        calls.append(process.pid)
        return False if len(calls) <= 3 else real(process)

    monkeypatch.setattr(_helper(), "kill_group_if_exited", still_exiting)
    real_signal = dsh._signal_dsh_group
    monkeypatch.setattr(
        dsh,
        "_signal_dsh_group",
        lambda proc, sig: (signals.append(sig), real_signal(proc, sig)),
    )
    monkeypatch.setattr(dsh, "DSH_OUTPUT_POLL_SECONDS", 0.01)
    failures: list[str] = []
    assert _supervised(tmp_path, _fake(tmp_path), failures) == (0, [])
    assert signals == []  # the exited group was signalled by the helper only
    assert len(calls) == 4 and failures == []
    assert _gone(_pid(tmp_path, "gc.pid"), tmp_path)
    assert _reaped(_pid(tmp_path, "leader.pid"))


def test_dsh_turn_reports_a_leader_never_seen_exited(tmp_path, monkeypatch, reap_ours):
    real = _helper().kill_group_if_exited
    held = []

    def never(process):
        held.append(process)
        return False

    monkeypatch.setattr(_helper(), "kill_group_if_exited", never)
    monkeypatch.setattr(dsh, "DSH_KILL_SETTLE_SECONDS", 0.5)
    failures: list[str] = []
    try:
        rc, reasons = _supervised(tmp_path, _fake(tmp_path), failures)
        assert failures == ["DSH_LEADER_NOT_EXITED"]
        assert (rc, reasons) == (125, [])  # DSH was never reaped: no exit code to keep
        assert held[-1].returncode is None
    finally:
        if held:
            assert real(held[-1])  # this test's own exited DSH: kill its group and reap it
    assert _gone(_pid(tmp_path, "gc.pid"), tmp_path)


def test_dsh_turn_interrupted_kills_and_reaps_the_group(tmp_path, monkeypatch, reap_ours):
    class Boom(Exception):
        pass

    class Exploding:
        steps = compactions = 0

        def feed_line(self, line):
            raise Boom(line)

    exe = _fake(tmp_path, linger=30, first_line="first")
    failures: list[str] = []
    started = time.monotonic()
    with pytest.raises(Boom):
        _supervised(tmp_path, exe, failures, watchdog=Exploding())
    assert time.monotonic() - started < 15
    assert failures == []
    assert _gone(_pid(tmp_path, "gc.pid"), tmp_path)
    assert _reaped(_pid(tmp_path, "leader.pid"))


# --- item 4: output held past the drain by a process outside the group is recorded ------------


@pytest.mark.parametrize(("exit_code", "expected_rc"), [(0, 125), (3, 3)], ids=["exit0", "exit3"])
def test_dsh_turn_records_output_held_by_a_process_outside_its_group(
    tmp_path, monkeypatch, reap_ours, exit_code, expected_rc
):
    monkeypatch.setattr(dsh, "DSH_OUTPUT_DRAIN_SECONDS", 1.0)
    exe = _fake(tmp_path, hold=True, escape=True, exit_code=exit_code, first_line="out")
    failures: list[str] = []
    started = time.monotonic()
    try:
        rc, reasons = _supervised(tmp_path, exe, failures)
        assert (rc, reasons) == (expected_rc, [])
        assert failures == ["DSH_OUTPUT_DRAIN_TIMEOUT"]
        assert time.monotonic() - started < 15
        assert (tmp_path / "log").read_text(encoding="utf-8") == "out\n"
        assert _reaped(_pid(tmp_path, "leader.pid"))
    finally:
        escaped = _pid(tmp_path, "gc.pid")  # left the group: the turn cannot reach it
        if _ours_alive(escaped, tmp_path):
            os.kill(escaped, signal.SIGKILL)


def test_dsh_turn_drain_reaching_eof_records_nothing(tmp_path, reap_ours):
    failures: list[str] = []
    rc, reasons = _supervised(tmp_path, _fake(tmp_path, hold=True), failures)
    assert (rc, reasons, failures) == (0, [], [])


# --- item 5: ci_gate.run_step refuses shell expansion it would not do ------------------------


@pytest.mark.parametrize("arg", ["$HOME", "${HOME}", "$(id)", "`id`"])
def test_ci_gate_step_refuses_shell_expansion_without_running(tmp_path, monkeypatch, arg):
    from scripts.ops import ci_gate

    monkeypatch.setattr(ci_gate, "ROOT", tmp_path)
    marker = tmp_path / "ran"
    exe = tmp_path / "step3076"
    exe.write_text(f"#!{sys.executable}\nopen({str(marker)!r}, 'w').close()\n", encoding="utf-8")
    exe.chmod(0o755)
    success, err = ci_gate.run_step("probe", f'"{exe}" {arg}')
    assert success is False
    assert "refused (no shell)" in err
    assert not marker.exists()
    summary = (tmp_path / ".nexus" / "reports" / "last_failure_summary.txt").read_text()
    assert "Exit Code: 2" in summary


def test_ci_gate_step_passes_pytest_node_ids_with_brackets(tmp_path, monkeypatch):
    from scripts.ops import ci_gate

    monkeypatch.setattr(ci_gate, "ROOT", tmp_path)
    out = tmp_path / "argv"
    exe = tmp_path / "step3076"
    exe.write_text(
        f"#!{sys.executable}\nimport sys\nopen({str(out)!r}, 'w').write('|'.join(sys.argv[1:]))\n",
        encoding="utf-8",
    )
    exe.chmod(0o755)
    success, _ = ci_gate.run_step("probe", f'"{exe}" tests/x.py::t[a-1] -q --junitxml="a b.xml"')
    assert success is True
    assert out.read_text() == "tests/x.py::t[a-1]|-q|--junitxml=a b.xml"
