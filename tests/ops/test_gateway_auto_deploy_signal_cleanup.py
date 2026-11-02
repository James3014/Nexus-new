"""A SIGTERM/SIGHUP to the auto-deployer never leaves a child group running (#3199).

The deployer starts the spare-probe candidate Gateway and its read-only
``run_bounded`` probes in their own sessions.  Every process here is started by
the test itself (a short-lived fake candidate or probe), the signals go only to
this test process or those children, and nothing touches a real Gateway,
LaunchAgent or deployer state dir.
"""

from __future__ import annotations

import contextlib
import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Iterator

import pytest

from scripts.ops import nexus_gateway_auto_deploy as ad
from tests.ops.test_nexus_gateway_auto_deploy import (  # noqa: F401 - pytest fixtures
    FakeHost,
    FakeProber,
    _core_origin,
    _rie_origin,
    cfg,
    cycle,
)

# A stand-in candidate Gateway: writes its pid, then sleeps (bounded).  With
# "stubborn" it ignores SIGTERM and instead sends one SIGTERM to its parent
# (the test process), so the deployer is signalled while stop() waits.
FAKE_CANDIDATE = """
import os, signal, sys, time
from pathlib import Path

if len(sys.argv) > 2 and sys.argv[2] == "stubborn":
    signal.signal(signal.SIGTERM, lambda *_: os.kill(os.getppid(), signal.SIGTERM))
out = Path(sys.argv[1])
tmp = out.with_name(out.name + ".tmp")
tmp.write_text(str(os.getpid()))
tmp.replace(out)
time.sleep(30)
"""


class _RealStartHost(FakeHost):
    """FakeHost whose candidate start/stop is the real one (a plain /bin/sh command)."""

    shell = "/bin/sh"
    start = ad.Host.start


@contextlib.contextmanager
def _sentinel_handlers() -> Iterator[list[int]]:
    """Install recording handlers for SIGTERM/SIGHUP; restore the originals after."""
    seen: list[int] = []

    def sentinel(signum: int, _frame: Any) -> None:
        seen.append(signum)

    originals = {s: signal.getsignal(s) for s in (signal.SIGTERM, signal.SIGHUP)}
    try:
        for s in originals:
            signal.signal(s, sentinel)
        yield seen
    finally:
        for s, handler in originals.items():
            signal.signal(s, handler)


def _wait_file(path: Path, timeout: float = 10.0) -> str:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return path.read_text()
        time.sleep(0.02)
    raise AssertionError(f"{path} never appeared")


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    stat = subprocess.run(
        ["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True, check=False
    ).stdout.strip()
    return bool(stat) and not stat.startswith("Z")


def _gone_within(pid: int, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _alive(pid):
            return True
        time.sleep(0.05)
    return not _alive(pid)


def _candidate_script(tmp_path: Path) -> Path:
    script = tmp_path / "fake-candidate.py"
    script.write_text(FAKE_CANDIDATE)
    return script


def _spare_only_wrapper(monkeypatch: pytest.MonkeyPatch, command: str) -> None:
    """The spare-probe candidate runs ``command``; the live wrapper stays real."""
    real = ad.wrapper_command

    def fake(*args: Any, **kwargs: Any) -> str:
        port = args[3] if len(args) > 3 else kwargs.get("port")
        return real(*args, **kwargs) if port is None else command

    monkeypatch.setattr(ad, "wrapper_command", fake)


@pytest.mark.parametrize("signum", [signal.SIGTERM, signal.SIGHUP])
def test_signal_during_probe_stops_candidate_and_cleans_probe_state(
    cfg: ad.Config,  # noqa: F811 - pytest fixture
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    signum: int,
) -> None:
    pidfile = tmp_path / "candidate.pid"
    script = _candidate_script(tmp_path)
    _spare_only_wrapper(monkeypatch, f'exec "{sys.executable}" "{script}" "{pidfile}"')
    seen: dict[str, Any] = {}

    def hook(call: dict[str, Any]) -> None:
        seen["pid"] = int(_wait_file(pidfile))
        seen["record"] = json.loads(cfg.probe_candidate_file.read_text())
        seen["state"] = sorted(p.name for p in cfg.probe_state_root.iterdir())
        os.kill(os.getpid(), signum)
        time.sleep(2)  # the handler raises here

    with _sentinel_handlers() as delivered:
        with pytest.raises(ad.DeployerTerminated) as info:
            cycle(cfg, _RealStartHost(), FakeProber(hook=hook))
        restored = {s: signal.getsignal(s) for s in (signal.SIGTERM, signal.SIGHUP)}
    assert info.value.signum == signum
    assert delivered == []  # the deployer's handler took it, not the previous one
    assert all(getattr(h, "__name__", "") == "sentinel" for h in restored.values())
    # The candidate group was stopped and reaped; its probe state and record are gone.
    assert not _alive(seen["pid"])
    assert seen["record"]["pid"] == seen["pid"]
    assert seen["record"]["entrypoint"].endswith(ad.ENTRYPOINT)
    assert len(seen["state"]) == 1
    assert list(cfg.probe_state_root.iterdir()) == []
    assert not cfg.probe_candidate_file.exists()


def test_probe_leaves_an_ignored_sighup_ignored(
    cfg: ad.Config,  # noqa: F811 - pytest fixture
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A deployer started under nohup keeps ignoring SIGHUP during and after the probe."""
    pidfile = tmp_path / "candidate.pid"
    script = _candidate_script(tmp_path)
    _spare_only_wrapper(monkeypatch, f'exec "{sys.executable}" "{script}" "{pidfile}"')
    seen: dict[str, Any] = {}

    def hook(call: dict[str, Any]) -> None:
        seen["pid"] = int(_wait_file(pidfile))
        seen["during"] = signal.getsignal(signal.SIGHUP)
        os.kill(os.getpid(), signal.SIGHUP)  # ignored: the probe goes on
        time.sleep(0.05)
        os.kill(os.getpid(), signal.SIGTERM)
        time.sleep(2)  # the handler raises here

    with _sentinel_handlers() as delivered:
        signal.signal(signal.SIGHUP, signal.SIG_IGN)
        with pytest.raises(ad.DeployerTerminated) as info:
            cycle(cfg, _RealStartHost(), FakeProber(hook=hook))
        after = signal.getsignal(signal.SIGHUP)
    assert info.value.signum == signal.SIGTERM
    assert seen["during"] is signal.SIG_IGN
    assert after is signal.SIG_IGN
    assert delivered == []
    assert not _alive(seen["pid"])


def test_non_python_handler_is_left_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    """``getsignal()`` None means a handler Python did not install: never replace it."""
    real_getsignal = signal.getsignal

    def getsignal(signum: int) -> Any:
        return None if signum == signal.SIGHUP else real_getsignal(signum)

    with _sentinel_handlers():
        before = real_getsignal(signal.SIGHUP)
        monkeypatch.setattr(ad.signal, "getsignal", getsignal)
        with ad.termination_raises():
            during = real_getsignal(signal.SIGHUP)
            term_during = real_getsignal(signal.SIGTERM)
        monkeypatch.undo()
        after = real_getsignal(signal.SIGHUP)
    assert during is before
    assert after is before
    assert getattr(term_during, "__name__", "") == "_raise"


def test_signal_while_stopping_a_stubborn_candidate_kills_its_group(
    tmp_path: Path,
) -> None:
    pidfile = tmp_path / "candidate.pid"
    script = _candidate_script(tmp_path)
    host = ad.Host()
    host.shell = "/bin/sh"
    stop = host.start(f'exec "{sys.executable}" "{script}" "{pidfile}" stubborn', tmp_path / "log")
    proc = stop.proc  # type: ignore[attr-defined]
    try:
        _wait_file(pidfile)
        with _sentinel_handlers(), ad.termination_raises():
            # SIGTERM to the group makes the candidate signal us while stop() waits.
            with pytest.raises(ad.DeployerTerminated):
                stop()
        with contextlib.suppress(subprocess.TimeoutExpired):
            proc.wait(timeout=10)
        assert proc.returncode == -signal.SIGKILL
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()


def test_interrupted_start_stops_the_group_before_raising(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pidfile = tmp_path / "candidate.pid"
    script = _candidate_script(tmp_path)
    made: list[Any] = []

    class Interrupted(ad._CandidateProcess):
        def __init__(self, proc: Any, log: Any) -> None:
            super().__init__(proc, log)
            made.append(self)
            if len(made) == 1:
                _wait_file(pidfile)  # the candidate really runs
                raise ad.DeployerTerminated(signal.SIGTERM)

    monkeypatch.setattr(ad, "_CandidateProcess", Interrupted)
    host = ad.Host()
    host.shell = "/bin/sh"
    try:
        with pytest.raises(ad.DeployerTerminated):
            host.start(f'exec "{sys.executable}" "{script}" "{pidfile}"', tmp_path / "log")
        assert made, "Popen never ran"
        assert made[0].proc.poll() is not None
    finally:
        for candidate in made:
            if candidate.proc.poll() is None:
                candidate.proc.kill()
                candidate.proc.wait()


RUN_BOUNDED_PROBE = """
import os, signal, subprocess, sys, time
g = subprocess.Popen(
    [sys.executable, "-c", "import time; time.sleep(30)", sys.argv[2]],
    stdout=subprocess.DEVNULL,
)
open(sys.argv[1], "w").write(str(g.pid))
os.kill(os.getppid(), signal.SIGTERM)
time.sleep(3)
print("done")
"""


def test_signal_during_run_bounded_kills_the_probe_group(tmp_path: Path) -> None:
    pidfile = tmp_path / "grandchild.pid"
    marker = f"nexus-3199-{os.getpid()}-{time.monotonic_ns()}"
    argv = [sys.executable, "-c", RUN_BOUNDED_PROBE, str(pidfile), marker]
    grandchild = None
    try:
        with _sentinel_handlers() as delivered:
            with pytest.raises(ad.DeployerTerminated):
                ad.Host().run_bounded(argv, timeout=20)
        assert delivered == []
        grandchild = int(_wait_file(pidfile))
        assert _gone_within(grandchild, 10), "probe group outlived the deployer signal"
    finally:
        if grandchild is None and pidfile.exists():
            grandchild = int(pidfile.read_text())
        if grandchild is not None and _alive(grandchild):
            identity = ad.Host().process_identity(grandchild)
            if identity and marker in identity["command"] and identity["pgid"] != os.getpgrp():
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(identity["pgid"], signal.SIGKILL)


def test_run_bounded_off_the_main_thread_installs_no_handler() -> None:
    out: list[Any] = []

    def worker() -> None:
        try:
            out.append(ad.Host().run_bounded([sys.executable, "-c", "print('ok')"], timeout=20))
        except BaseException as exc:  # noqa: BLE001 - reported below
            out.append(exc)

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join(30)
    assert out == [(0, "ok\n")]


def test_second_signal_during_cleanup_is_absorbed_and_handlers_restored() -> None:
    with _sentinel_handlers() as delivered:
        before = {s: signal.getsignal(s) for s in (signal.SIGTERM, signal.SIGHUP)}
        with ad.termination_raises():
            with pytest.raises(ad.DeployerTerminated):
                os.kill(os.getpid(), signal.SIGTERM)
                time.sleep(1)
            # Cleanup in progress: another signal must not cut it short.
            os.kill(os.getpid(), signal.SIGHUP)
            time.sleep(0.05)
        after = {s: signal.getsignal(s) for s in (signal.SIGTERM, signal.SIGHUP)}
    assert after == before
    assert delivered == []


# ---------------------------------------------------------------- startup sweep


def _leftover(tmp_path: Path, *, leader: bool = True) -> tuple[subprocess.Popen, Path]:
    """A fake candidate an earlier, killed cycle left behind (started by this test)."""
    entry = tmp_path / "deploy" / ad.ENTRYPOINT
    entry.parent.mkdir(parents=True, exist_ok=True)
    entry.write_text(FAKE_CANDIDATE)
    pidfile = tmp_path / "leftover.pid"
    proc = subprocess.Popen(
        [sys.executable, str(entry), str(pidfile)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=leader,
    )
    _wait_file(pidfile)
    # It is not our child in real life; reap it promptly like launchd would.
    threading.Thread(target=proc.wait, daemon=True).start()
    return proc, entry


def _write_record(config: ad.Config, **record: Any) -> Path:
    probe_state = config.probe_state_root / "a-left"
    (probe_state / "nested").mkdir(parents=True)
    record.setdefault("probe_state", str(probe_state))
    config.probe_candidate_file.write_text(json.dumps(record))
    return probe_state


def test_startup_sweep_stops_a_recorded_leftover_candidate(
    cfg: ad.Config,  # noqa: F811 - pytest fixture
    tmp_path: Path,
) -> None:
    proc, entry = _leftover(tmp_path)
    try:
        identity = ad.Host().process_identity(proc.pid)
        assert identity is not None and identity["pgid"] == proc.pid
        probe_state = _write_record(
            cfg, pid=proc.pid, started=identity["started"], entrypoint=str(entry)
        )
        result = cycle(cfg, FakeHost(), FakeProber())
        assert result["probe_sweep"] == {"action": "STOPPED", "pid": proc.pid}
        proc.wait(timeout=10)
        assert not probe_state.exists()
        assert not cfg.probe_candidate_file.exists()
        assert result["status"] == "DEPLOYED"  # the cycle itself goes on
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()


@pytest.mark.parametrize("mismatch", ["started", "entrypoint", "not_leader"])
def test_startup_sweep_never_signals_a_process_it_cannot_identify(
    cfg: ad.Config,  # noqa: F811 - pytest fixture
    tmp_path: Path,
    mismatch: str,
) -> None:
    proc, entry = _leftover(tmp_path, leader=mismatch != "not_leader")
    try:
        identity = ad.Host().process_identity(proc.pid)
        assert identity is not None
        record = {"pid": proc.pid, "started": identity["started"], "entrypoint": str(entry)}
        if mismatch == "started":
            record["started"] = "Thu Jan 1 00:00:00 1970"
        elif mismatch == "entrypoint":
            record["entrypoint"] = str(tmp_path / "other" / ad.ENTRYPOINT)
        probe_state = _write_record(cfg, **record)
        result = cycle(cfg, FakeHost(), FakeProber())
        assert result["probe_sweep"] == {"action": "NOT_OURS", "pid": proc.pid}
        time.sleep(0.3)
        assert proc.poll() is None, "an unidentified process was signalled"
        # Nothing of the record can still run: its state and the record go.
        assert not probe_state.exists()
        assert not cfg.probe_candidate_file.exists()
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()


def test_startup_sweep_is_skipped_on_a_dry_run(
    cfg: ad.Config,  # noqa: F811 - pytest fixture
    tmp_path: Path,
) -> None:
    probe_state = _write_record(
        cfg,
        pid=2**22 + 7,
        started="Thu Jan 1 00:00:00 1970",
        entrypoint=str(tmp_path / ad.ENTRYPOINT),
    )
    result = cycle(cfg, FakeHost(), FakeProber(), dry_run=True)
    assert "probe_sweep" not in result
    assert cfg.probe_candidate_file.exists()
    assert probe_state.exists()


def test_startup_sweep_keeps_a_probe_state_path_outside_the_probe_root(
    cfg: ad.Config,  # noqa: F811 - pytest fixture
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside-probe-root"
    (outside / "keep").mkdir(parents=True)
    nested = cfg.probe_state_root / "a" / "b"
    nested.mkdir(parents=True)
    for probe_state in (outside, nested):
        cfg.probe_candidate_file.write_text(
            json.dumps({"pid": "not-a-pid", "probe_state": str(probe_state)})
        )
        assert ad.sweep_probe_candidate(cfg, FakeHost()) == {
            "action": "RECORD_INVALID",
            "pid": None,
        }
        assert probe_state.is_dir(), probe_state
        assert not cfg.probe_candidate_file.exists()


class _NoPsHost(FakeHost):
    def process_identity(self, pid: int) -> dict[str, Any] | None:  # type: ignore[override]
        raise AssertionError(f"ps must not run for pid {pid}")


@pytest.mark.parametrize("pid", [1, 0, -1])
def test_startup_sweep_refuses_pid_one_and_below_without_ps(
    cfg: ad.Config,  # noqa: F811 - pytest fixture
    tmp_path: Path,
    pid: int,
) -> None:
    _write_record(
        cfg,
        pid=pid,
        started="Thu Jan 1 00:00:00 1970",
        entrypoint=str(tmp_path / ad.ENTRYPOINT),
    )
    assert ad.sweep_probe_candidate(cfg, _NoPsHost()) == {"action": "RECORD_INVALID", "pid": pid}
    assert not cfg.probe_candidate_file.exists()


class _PidStop:
    """A stop callable with a pid, for a candidate that is never really started."""

    def __init__(self, pid: int) -> None:
        self.pid = pid
        self.stopped = 0

    def __call__(self) -> None:
        self.stopped += 1


class _SurvivorHost(FakeHost):
    """Every pid matches its record, but no group can be stopped."""

    def __init__(self, entrypoint: str) -> None:
        super().__init__()
        self.entrypoint = entrypoint
        self.identity_calls: list[int] = []

    def start(self, command, log_path):  # type: ignore[override]
        self.started.append(command)
        return _PidStop(4242)

    def process_identity(self, pid: int) -> dict[str, Any] | None:  # type: ignore[override]
        self.identity_calls.append(pid)
        return {"pgid": pid, "started": "Mon Nov 2 13:00:00 2026", "command": self.entrypoint}

    def stop_process_group(self, pgid: int) -> bool:  # type: ignore[override]
        return False


def test_a_record_the_sweep_kept_is_not_overwritten_by_the_next_probe(
    cfg: ad.Config,  # noqa: F811 - pytest fixture
    tmp_path: Path,
) -> None:
    entrypoint = str(tmp_path / "old" / ad.ENTRYPOINT)
    record = {"pid": 777, "started": "Mon Nov 2 13:00:00 2026", "entrypoint": entrypoint}
    _write_record(cfg, **record)
    kept = cfg.probe_candidate_file.read_text()
    host = _SurvivorHost(entrypoint)
    result = cycle(cfg, host, FakeProber())
    assert result["probe_sweep"] == {"action": "SURVIVED", "pid": 777}
    assert host.started  # the cycle still probed its own candidate
    assert cfg.probe_candidate_file.read_text() == kept
    assert 4242 not in host.identity_calls


def test_a_failed_record_write_does_not_fail_the_attempt(
    cfg: ad.Config,  # noqa: F811 - pytest fixture
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_write = ad._atomic_write

    def atomic_write(path: Path, data: bytes, mode: int = 0o644) -> None:
        if path == cfg.probe_candidate_file:
            raise OSError(28, "No space left on device")
        real_write(path, data, mode)

    monkeypatch.setattr(ad, "_atomic_write", atomic_write)
    host = _SurvivorHost(str(tmp_path / ad.ENTRYPOINT))
    result = cycle(cfg, host, FakeProber())
    assert result["status"] == "DEPLOYED"
    assert host.identity_calls == [4242]
    assert not cfg.probe_candidate_file.exists()
