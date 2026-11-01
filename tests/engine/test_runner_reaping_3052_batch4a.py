"""#3052: the OpenCode worker transport and the task runner's command runner leave no child behind.

``OpenCodeWorkerTransport._run`` (the EIA default worker backend) started the worker in its own
session but never killed that process group after a normal exit, and on a timeout its last
``communicate()`` had no bound. ``task_runner.run_shell`` ran task ``run`` strings through
``run_command_string`` without ``reap_process_group``. Both now kill the group on every exit.

The stray process is a double-forked Python grandchild (no shell ``&``, no ``setsid``), so it
is reparented away from the runner but stays in the runner's process group. Only processes this
test started are ever signalled: each records its pid, and cleanup first checks that ``ps``
shows this test's unique tmp path in its command line.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

GRANDCHILD = r"""#!{python}
import os, sys, time
PIDFILE = {pidfile!r}
pid = os.fork()
if pid == 0:
    if os.fork() == 0:
        fd = os.open(os.devnull, os.O_RDWR)
        for n in (0, 1, 2):
            os.dup2(fd, n)
        with open(PIDFILE + ".tmp", "w") as f:
            f.write(str(os.getpid()))
        os.replace(PIDFILE + ".tmp", PIDFILE)
        time.sleep(60)
        os._exit(0)
    os._exit(0)
os.waitpid(pid, 0)
print("{{}}", flush=True)
sys.exit(0)
"""

# The leader never exits on its own; a forked child keeps the inherited stdout open, in the
# leader's process group or (``setsid``) in a session of its own.
HOLDER = r"""#!{python}
import os, sys, time
PIDFILE = {pidfile!r}
if os.fork() == 0:
    if {setsid!r}:
        os.setsid()
    with open(PIDFILE + ".tmp", "w") as f:
        f.write(str(os.getpid()))
    os.replace(PIDFILE + ".tmp", PIDFILE)
    time.sleep({sleep})
    os._exit(0)
print("partial", flush=True)
time.sleep({sleep})
"""


def _script(tmp_path: Path, name: str, template: str, **fields: object) -> tuple[Path, Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    pid_file = tmp_path / f"{name}.pid"
    script = bin_dir / name
    script.write_text(template.format(python=sys.executable, pidfile=str(pid_file), **fields))
    script.chmod(0o755)
    return script, pid_file


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    state = subprocess.run(
        ["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True, check=False
    ).stdout.strip()
    return bool(state) and not state.startswith("Z")


def _ours(pid: int, marker: Path) -> bool:
    command = subprocess.run(
        ["ps", "-o", "command=", "-p", str(pid)], capture_output=True, text=True, check=False
    ).stdout
    return str(marker) in command


def _read_pid(pid_file: Path) -> int:
    for _ in range(100):
        if pid_file.exists() and pid_file.read_text().strip():
            break
        time.sleep(0.05)
    return int(pid_file.read_text().strip())


def _kill_if_ours(pid: int, marker: Path) -> None:
    if _alive(pid) and _ours(pid, marker):
        os.kill(pid, signal.SIGKILL)


def _check_gone(pid_file: Path, marker: Path) -> None:
    pid = _read_pid(pid_file)
    try:
        deadline = time.monotonic() + 3
        while _alive(pid) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert not _alive(pid), f"grandchild {pid} in the runner's process group outlived it"
    finally:
        _kill_if_ours(pid, marker)


def _workspace(tmp_path: Path) -> tuple[Path, Path]:
    ws = tmp_path / "ws"
    ws.mkdir()
    artifact = tmp_path / "artifact.json"
    artifact.write_text("{}")
    return ws, artifact


def test_opencode_worker_normal_exit_leaves_no_grandchild(tmp_path):
    from nexus.services.external_intelligence_fanout import OpenCodeWorkerTransport

    exe, pid_file = _script(tmp_path, "opencode", GRANDCHILD)
    ws, art = _workspace(tmp_path)
    OpenCodeWorkerTransport(executable=str(exe), timeout=20).run_new(
        prompt="p", artifact_path=str(art), workspace_path=str(ws)
    )
    _check_gone(pid_file, tmp_path)


def test_opencode_worker_timeout_is_outcome_unknown_and_leaves_no_grandchild(tmp_path):
    from nexus.services.external_intelligence_fanout import OpenCodeWorkerTransport

    exe, pid_file = _script(tmp_path, "opencode", HOLDER, setsid=False, sleep=30)
    ws, art = _workspace(tmp_path)
    result = OpenCodeWorkerTransport(executable=str(exe), timeout=1).run_new(
        prompt="p", artifact_path=str(art), workspace_path=str(ws)
    )
    assert (result.status, result.error) == ("OPENCODE_OUTCOME_UNKNOWN", "provider_timeout")
    assert (result.process_started, result.outcome_unknown, result.retry_safe) == (
        True,
        True,
        False,
    )
    _check_gone(pid_file, tmp_path)


def test_opencode_worker_timeout_is_bounded_when_a_pipe_is_held_outside_the_group(tmp_path):
    from nexus.services.external_intelligence_fanout import OpenCodeWorkerTransport

    # The holder left the group (setsid), so no group kill reaches it; the transport must still
    # return without waiting for it to close the pipe.
    exe, pid_file = _script(tmp_path, "opencode", HOLDER, setsid=True, sleep=30)
    ws, art = _workspace(tmp_path)
    started = time.monotonic()
    try:
        result = OpenCodeWorkerTransport(executable=str(exe), timeout=1).run_new(
            prompt="p", artifact_path=str(art), workspace_path=str(ws)
        )
        elapsed = time.monotonic() - started
        assert (result.status, result.error) == ("OPENCODE_OUTCOME_UNKNOWN", "provider_timeout")
        assert elapsed < 15, f"transport waited {elapsed:.1f}s for a pipe held past its timeout"
    finally:
        _kill_if_ours(_read_pid(pid_file), tmp_path)


def test_opencode_worker_start_refused_spawns_nothing(tmp_path):
    from nexus.services.external_intelligence_fanout import OpenCodeWorkerTransport

    # Records that it ran and exits: nothing is left running if it is (wrongly) started.
    exe, pid_file = _script(
        tmp_path, "opencode", "#!{python}\nopen({pidfile!r}, 'w').write('started')\n"
    )
    ws, art = _workspace(tmp_path)
    previous = signal.signal(signal.SIGCHLD, signal.SIG_IGN)
    try:
        result = OpenCodeWorkerTransport(executable=str(exe), timeout=20).run_new(
            prompt="p", artifact_path=str(art), workspace_path=str(ws)
        )
    finally:
        signal.signal(signal.SIGCHLD, previous)
    assert result.status == "OPENCODE_START_REFUSED"
    assert (result.process_started, result.outcome_unknown) == (False, False)
    assert result.retry_safe is False
    time.sleep(0.5)
    assert not pid_file.exists()


def test_task_runner_run_shell_leaves_no_grandchild(tmp_path):
    from scripts.ops.task_runner import run_shell

    exe, pid_file = _script(tmp_path, "taskcmd3052", GRANDCHILD)
    rc, _out, _err = run_shell(str(exe), 20, cwd=tmp_path)
    assert rc == 0
    _check_gone(pid_file, tmp_path)


def test_task_runner_run_shell_timeout_leaves_no_grandchild(tmp_path):
    from scripts.ops.task_runner import run_shell

    exe, pid_file = _script(tmp_path, "taskcmd3052", HOLDER, setsid=False, sleep=30)
    rc, _out, err = run_shell(str(exe), 1, cwd=tmp_path)
    assert (rc, err) == (124, "timeout:1s")
    _check_gone(pid_file, tmp_path)


def test_opencode_worker_missing_executable_is_retry_safe(tmp_path):
    from nexus.services.external_intelligence_fanout import OpenCodeWorkerTransport

    ws, art = _workspace(tmp_path)
    result = OpenCodeWorkerTransport(executable=str(tmp_path / "missing" / "opencode")).run_new(
        prompt="p", artifact_path=str(art), workspace_path=str(ws)
    )
    assert (result.status, result.process_started, result.retry_safe) == (
        "OPENCODE_NOT_FOUND",
        False,
        True,
    )
