"""Terminating signals, undecodable output and unexpected errors in the local check (#3189).

Signal tests signal only processes this file started; the fake ``uv`` and Core sleep for a
bounded time and every recorded pid is killed only after its command line is checked.
"""

from __future__ import annotations

import fcntl
import importlib.machinery
import importlib.util
import json
import os
import shutil
import signal
import stat
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "nexus-core-issue-check-local"
PIN = "e" * 40
WORKFLOW = ".github/workflows/nexus-core-issue-completion.yml"
SIGNALS = [signal.SIGTERM, signal.SIGHUP, signal.SIGQUIT]
BOUND = 30  # seconds any fake child may live


def _load_module():
    loader = importlib.machinery.SourceFileLoader("nexus_core_issue_check_local_3189", str(SCRIPT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


# --- stubbed Popen: handler window, restore, threads ---


class FakeProc:
    pid = 424243

    def __init__(self, wait_action=None, running=True):
        self._wait_action = wait_action
        self._running = running
        self.returncode = None if running else 0

    def poll(self):
        return None if self._running else 0

    def wait(self, timeout=None):
        if self._running and self._wait_action is not None:
            action, self._wait_action = self._wait_action, None
            action()
        self._running = False
        self.returncode = 0
        return 0


def _stub(module, monkeypatch, popen):
    kills: list[tuple[int, int]] = []
    monkeypatch.setattr(module.subprocess, "Popen", popen)
    # Stands in for argv_command.kill_group_if_exited: the child's exit, then its group's kill
    # and reap (the kill there is not recorded here).
    monkeypatch.setattr(module, "_group_stopped_if_exited", lambda proc: proc.wait() == 0)
    monkeypatch.setattr(module.os, "killpg", lambda pid, sig: kills.append((pid, sig)))
    return kills


def _run(module, tmp_path):
    return module._run_with_timeout(
        ["uv", "tool", "install"], cwd=tmp_path, env={}, code="CORE_INSTALL_FAILED", timeout=5
    )


@pytest.fixture
def sentinel_handlers():
    """Distinct previous handlers for the three signals, restored afterwards."""

    def previous(signum, frame):
        raise AssertionError(f"signal {signum} reached the previous handler")

    old = {s: signal.signal(s, previous) for s in SIGNALS}
    yield previous
    for s, h in old.items():
        signal.signal(s, h)


@pytest.mark.parametrize("sig", SIGNALS)
def test_signal_during_the_wait_stops_the_group_and_restores_every_handler(
    tmp_path, monkeypatch, sentinel_handlers, sig
):
    module = _load_module()
    proc = FakeProc(lambda: os.kill(os.getpid(), sig))
    kills = _stub(module, monkeypatch, lambda *a, **k: proc)
    with pytest.raises(SystemExit) as exit_info:
        _run(module, tmp_path)
    assert exit_info.value.code == 128 + sig
    assert kills == [(proc.pid, signal.SIGKILL)]
    assert all(signal.getsignal(s) == sentinel_handlers for s in SIGNALS)


@pytest.mark.parametrize("sig", SIGNALS)
def test_handler_is_installed_before_the_child_is_spawned(
    tmp_path, monkeypatch, sentinel_handlers, sig
):
    module = _load_module()
    seen: dict[str, bool] = {}

    def popen(*a, **k):
        seen["owned"] = all(signal.getsignal(s) != sentinel_handlers for s in SIGNALS)
        # A signal landing right after the spawn must still unwind through the cleanup.
        os.kill(os.getpid(), sig)
        return FakeProc()

    _stub(module, monkeypatch, popen)
    with pytest.raises(SystemExit):
        _run(module, tmp_path)
    assert seen == {"owned": True}
    assert all(signal.getsignal(s) == sentinel_handlers for s in SIGNALS)


def test_signal_while_spawning_leaves_no_handler_behind(tmp_path, monkeypatch, sentinel_handlers):
    module = _load_module()

    def popen(*a, **k):
        os.kill(os.getpid(), signal.SIGHUP)  # delivered inside Popen, before a proc exists
        raise AssertionError("handler did not raise")

    kills = _stub(module, monkeypatch, popen)
    with pytest.raises(SystemExit):
        _run(module, tmp_path)
    assert kills == []
    assert all(signal.getsignal(s) == sentinel_handlers for s in SIGNALS)


def test_restore_runs_even_when_the_group_stop_fails(tmp_path, monkeypatch, sentinel_handlers):
    module = _load_module()
    proc = FakeProc(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    _stub(module, monkeypatch, lambda *a, **k: proc)

    def failing_stop(p):
        raise OSError("cannot stop")

    monkeypatch.setattr(module, "_stop_group", failing_stop)
    with pytest.raises(OSError):
        _run(module, tmp_path)
    assert all(signal.getsignal(s) == sentinel_handlers for s in SIGNALS)


def test_off_the_main_thread_no_handler_is_touched(tmp_path, monkeypatch):
    module = _load_module()
    _stub(module, monkeypatch, lambda *a, **k: FakeProc())
    results: list[object] = []

    def work():
        try:
            results.append(_run(module, tmp_path).returncode)
        except BaseException as exc:  # noqa: BLE001
            results.append(exc)

    before = {s: signal.getsignal(s) for s in SIGNALS}
    thread = threading.Thread(target=work)
    thread.start()
    thread.join(10)
    assert results == [0]
    assert {s: signal.getsignal(s) for s in SIGNALS} == before


# --- decoding and unexpected errors ---


def test_help_explains_what_the_install_timeout_bounds(capsys):
    module = _load_module()
    with pytest.raises(SystemExit):
        module.build_parser().parse_args(["--help"])
    text = " ".join(capsys.readouterr().out.split())
    assert "--install-timeout" in text
    assert "waiting on another run's install" in text
    assert "killed" in text and "exits 2" in text


def test_pointer_with_non_utf8_bytes_is_an_invalid_pointer(tmp_path):
    module = _load_module()
    pointer = tmp_path / "pointer"
    pointer.write_bytes(b"/tmp/\xff\xfe.json\n")
    with pytest.raises(module.LocalCheckError) as err:
        module.reported_receipt(pointer, tmp_path / "wt")
    assert err.value.code == "RECEIPT_POINTER_INVALID"


def test_main_maps_an_unexpected_exception_to_exit_2(monkeypatch, capsys):
    module = _load_module()

    def boom(args):
        raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")

    monkeypatch.setattr(module, "run_check", boom)
    assert module.main(["--issue", "1"]) == module.EXIT_ERROR
    out = json.loads(capsys.readouterr().out)
    assert out["error_code"] == "LOCAL_UNEXPECTED_ERROR"
    assert "UnicodeDecodeError" in out["error"]


def test_main_restores_the_handlers(monkeypatch, sentinel_handlers):
    module = _load_module()
    monkeypatch.setattr(module, "run_check", lambda args: ({"status": "VERIFIED"}, 0))
    assert module.main(["--issue", "1"]) == 0
    assert all(signal.getsignal(s) == sentinel_handlers for s in SIGNALS)


@pytest.mark.parametrize("sig", SIGNALS)
def test_a_signal_between_child_groups_still_unwinds_run_check(monkeypatch, sentinel_handlers, sig):
    module = _load_module()
    reached: list[str] = []

    def run_check(args):
        try:
            os.kill(os.getpid(), sig)  # outside any child group, e.g. during worktree setup
            reached.append("not unwound")
        finally:
            reached.append("cleanup")
        return {}, 0

    monkeypatch.setattr(module, "run_check", run_check)
    with pytest.raises(SystemExit) as exit_info:
        module.main(["--issue", "1"])
    assert exit_info.value.code == 128 + sig
    assert reached == ["cleanup"]
    assert all(signal.getsignal(s) == sentinel_handlers for s in SIGNALS)


# --- real processes ---


def _git(cwd, *args):
    return subprocess.run(
        ["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True, timeout=60
    ).stdout.strip()


def _command_of(pid: int) -> str:
    return subprocess.run(
        ["ps", "-o", "command=", "-p", str(pid)], capture_output=True, text=True, timeout=10
    ).stdout.strip()


def _alive(pid: int) -> bool:
    state = subprocess.run(
        ["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True, timeout=10
    ).stdout.strip()
    return bool(state) and not state.startswith("Z")


def _kill_recorded(pids_file: Path, tmp: Path) -> None:
    """Kill leftovers only if the pid still runs one of our fakes (sleep or a script in tmp)."""
    if not pids_file.exists():
        return
    for text in pids_file.read_text().split():
        pid = int(text)
        command = _command_of(pid)
        if command and (str(tmp) in command or command == f"sleep {BOUND}"):
            try:
                os.kill(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass


FAKE_UV = f"""#!/usr/bin/env python3
import os, subprocess, sys, time
from pathlib import Path

child = subprocess.Popen(["sleep", "{BOUND}"])
Path(os.environ["FAKE_PIDS"]).write_text(f"{{os.getpid()}} {{child.pid}}")
# Keep writing into the tool dir, as a live install would, until killed.
bindir = Path(os.environ["UV_TOOL_BIN_DIR"])
bindir.mkdir(parents=True, exist_ok=True)
end = time.monotonic() + {BOUND}
while time.monotonic() < end:
    (bindir / "heartbeat").write_text(str(time.monotonic()))
    time.sleep(0.1)
"""

FAKE_CERTIFY_SLOW = f"""#!/usr/bin/env python3
import os, subprocess, sys, time
from pathlib import Path

if sys.argv[1] == "issue-init":
    child = subprocess.Popen(["sleep", "{BOUND}"])
    Path(os.environ["FAKE_PIDS"]).write_text(f"{{os.getpid()}} {{child.pid}}")
    time.sleep({BOUND})
"""

FAKE_CERTIFY_BRIEF = """#!/usr/bin/env python3
import os, sys, time
from pathlib import Path

if sys.argv[1] == "issue-init":
    Path(os.environ["FAKE_PIDS"]).write_text(str(os.getpid()))
    time.sleep(2)
"""

FAKE_CERTIFY_BINARY_OUTPUT = """#!/usr/bin/env python3
import sys
sys.stdout.buffer.write(b"caf\\xe9 \\xff\\xfe not utf-8\\n")
sys.stdout.buffer.flush()
"""


def _executable(path: Path, text: str) -> Path:
    path.write_text(text)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


@pytest.fixture
def sandbox(tmp_path: Path):
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True)
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    (repo / ".github/workflows").mkdir(parents=True)
    (repo / WORKFLOW).write_text(f"env:\n  NEXUS_CORE_TOOL_PIN: {PIN}\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")
    _git(repo, "remote", "add", "origin", str(bare))
    _git(repo, "push", "-q", "origin", "main")
    _git(repo, "fetch", "-q", "origin", "main")
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    _executable(fakebin / "uv", FAKE_UV)
    pids = tmp_path / "pids"
    env = dict(
        os.environ,
        GITHUB_TOKEN="tok",
        FAKE_PIDS=str(pids),
        PYTHONDONTWRITEBYTECODE="1",
        PATH=f"{fakebin}{os.pathsep}{os.environ.get('PATH', '')}",
    )
    yield {"repo": repo, "tmp": tmp_path, "env": env, "pids": pids, "fakebin": fakebin}
    _kill_recorded(pids, tmp_path)


def _start(sandbox, *extra):
    cmd = [
        sys.executable,
        str(SCRIPT),
        "--issue",
        "7",
        "--repo-root",
        str(sandbox["repo"]),
        "--cache-root",
        str(sandbox["tmp"] / "cache"),
        "--output-dir",
        str(sandbox["tmp"] / "out"),
        "--no-fetch",
        *extra,
    ]
    return subprocess.Popen(
        cmd,
        env=sandbox["env"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,  # a signal to the script never reaches this test process
    )


def _wait_for(path: Path, limit: float = 20.0) -> None:
    deadline = time.monotonic() + limit
    while not path.exists() or not path.read_text().strip():
        assert time.monotonic() < deadline, f"{path} never appeared"
        time.sleep(0.05)
    time.sleep(0.3)  # let the script reach its wait


def _pids(sandbox) -> list[int]:
    return [int(p) for p in sandbox["pids"].read_text().split()]


def _assert_all_dead(pids: list[int]) -> None:
    deadline = time.monotonic() + 10
    while any(_alive(p) for p in pids) and time.monotonic() < deadline:
        time.sleep(0.1)
    assert not any(_alive(p) for p in pids)


@pytest.mark.parametrize("sig", SIGNALS)
def test_signal_during_the_uv_install_stops_the_group(sandbox, sig):
    proc = _start(sandbox)
    try:
        _wait_for(sandbox["pids"])
        os.kill(proc.pid, sig)
        proc.communicate(timeout=30)
        assert proc.returncode == 128 + sig
        _assert_all_dead(_pids(sandbox))
        lock_path = sandbox["tmp"] / "cache" / "tools" / f"{PIN}.lock"
        with open(lock_path, "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)  # free
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.communicate()
        _kill_recorded(sandbox["pids"], sandbox["tmp"])


@pytest.mark.parametrize("sig", SIGNALS)
def test_signal_while_core_runs_removes_the_worktree_and_stops_core(sandbox, sig):
    certify = _executable(sandbox["tmp"] / "fake-certify", FAKE_CERTIFY_SLOW)
    proc = _start(sandbox, "--certify-bin", str(certify))
    try:
        _wait_for(sandbox["pids"])
        assert len(_git(sandbox["repo"], "worktree", "list").splitlines()) == 2
        os.kill(proc.pid, sig)
        proc.communicate(timeout=30)
        assert proc.returncode == 128 + sig
        _assert_all_dead(_pids(sandbox))
        assert len(_git(sandbox["repo"], "worktree", "list").splitlines()) == 1
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.communicate()
        _kill_recorded(sandbox["pids"], sandbox["tmp"])


def test_non_utf8_core_output_is_a_local_error_not_a_verdict(sandbox):
    certify = _executable(sandbox["tmp"] / "fake-certify", FAKE_CERTIFY_BINARY_OUTPUT)
    proc = _start(sandbox, "--certify-bin", str(certify))
    stdout, stderr = proc.communicate(timeout=60)
    assert "Traceback" not in stderr, stderr
    out = json.loads(stdout)
    assert proc.returncode == 2
    # Core exited 0 without a receipt: reported as a local problem, with the output kept.
    assert out["error_code"] == "RECEIPT_MISSING"
    log = (sandbox["tmp"] / "out" / "issue-7-check.log").read_text(encoding="utf-8")
    assert "not utf-8" in log


def test_a_signal_inherited_as_ignored_stays_ignored(sandbox):
    """Under nohup a hangup must not end a run that would have finished (exit 2 here)."""
    certify = _executable(sandbox["tmp"] / "fake-certify", FAKE_CERTIFY_BRIEF)
    cmd = [
        sys.executable,
        str(SCRIPT),
        "--issue",
        "7",
        "--repo-root",
        str(sandbox["repo"]),
        "--cache-root",
        str(sandbox["tmp"] / "cache"),
        "--output-dir",
        str(sandbox["tmp"] / "out"),
        "--no-fetch",
        "--certify-bin",
        str(certify),
    ]
    proc = subprocess.Popen(
        cmd,
        env=sandbox["env"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
        preexec_fn=lambda: signal.signal(signal.SIGHUP, signal.SIG_IGN),
    )
    try:
        _wait_for(sandbox["pids"])
        os.kill(proc.pid, signal.SIGHUP)
        stdout, _ = proc.communicate(timeout=30)
        assert proc.returncode == 2
        assert json.loads(stdout)["error_code"] == "RECEIPT_MISSING"
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.communicate()
        _kill_recorded(sandbox["pids"], sandbox["tmp"])


# --- residuals from the verification of #3211: cleanup under signals, group left by Core ---


def test_a_signal_during_cleanup_is_held_until_the_cleanup_is_done(sentinel_handlers):
    module = _load_module()
    previous = module._raise_on_signals()
    reached: list[str] = []
    try:
        with pytest.raises(SystemExit) as exit_info:
            with module._signals_held():
                os.kill(os.getpid(), signal.SIGTERM)
                os.kill(os.getpid(), signal.SIGHUP)  # a second one: still held, first kept
                reached.append("cleanup finished")
        assert exit_info.value.code == 128 + signal.SIGTERM
        assert reached == ["cleanup finished"]
        # Nothing stays held: the next signal outside a held block raises at once.
        with pytest.raises(SystemExit) as again:
            os.kill(os.getpid(), signal.SIGQUIT)
        assert again.value.code == 128 + signal.SIGQUIT
    finally:
        module._restore_signals(previous)
    assert all(signal.getsignal(s) == sentinel_handlers for s in SIGNALS)


def test_a_handler_not_installed_from_python_is_left_in_place(monkeypatch, sentinel_handlers):
    """getsignal() returns None for it, which signal.signal() could not restore (#3189)."""
    module = _load_module()
    real = signal.getsignal
    monkeypatch.setattr(
        module.signal, "getsignal", lambda s: None if s == signal.SIGHUP else real(s)
    )
    previous = module._raise_on_signals()
    try:
        assert signal.SIGHUP not in previous
        assert real(signal.SIGHUP) == sentinel_handlers
        assert real(signal.SIGTERM) != sentinel_handlers
    finally:
        module._restore_signals(previous)
    assert all(real(s) == sentinel_handlers for s in SIGNALS)


def test_a_failed_install_of_a_later_handler_restores_the_earlier_ones(
    monkeypatch, sentinel_handlers
):
    module = _load_module()
    real = signal.signal
    failed: list[int] = []

    def flaky(signum, handler):
        if signum == signal.SIGHUP and not failed:
            failed.append(signum)
            raise ValueError("cannot install")
        return real(signum, handler)

    monkeypatch.setattr(module.signal, "signal", flaky)
    with pytest.raises(ValueError):
        module._raise_on_signals()
    assert failed == [signal.SIGHUP]
    assert all(signal.getsignal(s) == sentinel_handlers for s in SIGNALS)


FAKE_CERTIFY_LEAVES_GROUP_MEMBER = f"""#!/usr/bin/env python3
import os, subprocess, sys
from pathlib import Path

if sys.argv[1] == "issue-init":
    child = subprocess.Popen(["sleep", "{BOUND}"])
    Path(os.environ["FAKE_PIDS"]).write_text(f"{{os.getpid()}} {{child.pid}}")
sys.exit(1)
"""

FAKE_CERTIFY_FAILS = """#!/usr/bin/env python3
import sys
sys.exit(1)
"""


def _git_shim(sandbox, action: str) -> None:
    """A ``git`` first on PATH that runs *action* before a ``worktree remove``."""
    real_git = shutil.which("git")
    assert real_git
    marker = sandbox["tmp"] / "cleanup-started"
    _executable(
        sandbox["fakebin"] / "git",
        f'#!/bin/sh\ncase "$*" in *"worktree remove"*) echo started > "{marker}"; {action};; esac\n'
        f'exec "{real_git}" "$@"\n',
    )


def _registered_worktrees(sandbox) -> int:
    return len(_git(sandbox["repo"], "worktree", "list").splitlines())


def test_a_member_left_in_cores_group_is_stopped_when_core_exits(sandbox):
    """Core exits first and leaves a process in its group: it does not run on (#3189)."""
    certify = _executable(sandbox["tmp"] / "fake-certify", FAKE_CERTIFY_LEAVES_GROUP_MEMBER)
    proc = _start(sandbox, "--certify-bin", str(certify))
    try:
        proc.communicate(timeout=30)
        assert proc.returncode == 1
        _assert_all_dead(_pids(sandbox))
        assert _registered_worktrees(sandbox) == 1
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.communicate()
        _kill_recorded(sandbox["pids"], sandbox["tmp"])


@pytest.mark.parametrize("twice", [False, True], ids=["one-signal", "second-signal"])
@pytest.mark.parametrize("sig", SIGNALS)
def test_a_signal_during_the_normal_cleanup_still_removes_the_worktree(sandbox, sig, twice):
    certify = _executable(sandbox["tmp"] / "fake-certify", FAKE_CERTIFY_FAILS)
    _git_shim(sandbox, "sleep 2")
    proc = _start(sandbox, "--certify-bin", str(certify))
    try:
        _wait_for(sandbox["tmp"] / "cleanup-started")
        os.kill(proc.pid, sig)
        if twice:
            time.sleep(0.2)
            os.kill(proc.pid, signal.SIGTERM if sig != signal.SIGTERM else signal.SIGHUP)
        stdout, _ = proc.communicate(timeout=30)
        assert proc.returncode == 128 + sig
        assert stdout == ""  # interrupted: no summary, as for any signal exit
        assert _registered_worktrees(sandbox) == 1
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.communicate()


def test_a_worktree_remove_that_did_not_finish_is_still_pruned(sandbox):
    """Its git killed (a hangup to the whole terminal group): the entry is still pruned."""
    certify = _executable(sandbox["tmp"] / "fake-certify", FAKE_CERTIFY_FAILS)
    _git_shim(sandbox, "exit 129")
    proc = _start(sandbox, "--certify-bin", str(certify))
    proc.communicate(timeout=60)
    assert proc.returncode == 1
    assert _registered_worktrees(sandbox) == 1


def test_sigterm_still_cleans_up_when_sighup_is_inherited_as_ignored(sandbox):
    certify = _executable(sandbox["tmp"] / "fake-certify", FAKE_CERTIFY_SLOW)
    cmd = [
        sys.executable,
        str(SCRIPT),
        "--issue",
        "7",
        "--repo-root",
        str(sandbox["repo"]),
        "--cache-root",
        str(sandbox["tmp"] / "cache"),
        "--output-dir",
        str(sandbox["tmp"] / "out"),
        "--no-fetch",
        "--certify-bin",
        str(certify),
    ]
    proc = subprocess.Popen(
        cmd,
        env=sandbox["env"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
        preexec_fn=lambda: signal.signal(signal.SIGHUP, signal.SIG_IGN),
    )
    try:
        _wait_for(sandbox["pids"])
        os.kill(proc.pid, signal.SIGTERM)
        proc.communicate(timeout=30)
        assert proc.returncode == 128 + signal.SIGTERM
        _assert_all_dead(_pids(sandbox))
        assert _registered_worktrees(sandbox) == 1
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.communicate()
        _kill_recorded(sandbox["pids"], sandbox["tmp"])
