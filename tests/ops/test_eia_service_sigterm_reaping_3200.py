"""#3200: stopping the EIA service the way the daily bootout does leaves no helper running.

launchd stops the job with SIGTERM and SIGKILLs it 20 s later. The fanout runs its OpenCode
and open-swe helpers from worker threads, each in its own process group, so neither the
service's exit nor launchd's group kill reaches them. These tests start the real ``daemon``
loop in a child process whose poll runs both helper kinds from worker threads, as the fanout
does, send that process SIGTERM, and check every helper and its own child is gone well before
launchd's SIGKILL, with the run recorded as interrupted. Only processes these tests start are
ever signalled.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import textwrap
import time
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
# launchd's default ExitTimeOut: the time between SIGTERM and SIGKILL at bootout.
LAUNCHD_EXIT_TIMEOUT_SECONDS = 20.0

DRIVER = textwrap.dedent(
    """
    import sys
    from concurrent.futures import ThreadPoolExecutor
    from pathlib import Path

    import scripts.ops.external_intelligence_service as service
    from nexus.services.external_intelligence_fanout import OpenCodeWorkerTransport
    from nexus.services.open_swe_external_intelligence import _runtime_call

    work, helper, mode = Path(sys.argv[1]), sys.argv[2], sys.argv[3]


    def helpers_poll(config):
        # As AdaptiveWorkerFanoutRuntime: helpers run from "nexus-ei" worker threads.
        opencode = OpenCodeWorkerTransport(executable=helper, timeout=300)
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="nexus-ei") as executor:
            futures = [
                executor.submit(
                    opencode.run_new,
                    prompt="p",
                    artifact_path=str(work / "artifact.json"),
                    workspace_path=str(work / "opencode"),
                ),
                executor.submit(_runtime_call, helper, {"op": "x"}, provider_id="", timeout=300),
            ]
            for future in futures:
                future.result()
        return {"status": "COMPLETE"}


    def idle_poll(config):
        return {"status": "IDLE"}


    service.run_once = helpers_poll if mode == "helpers" else idle_poll
    config_path = work / "config.json"
    config = service.ServiceConfig(
        repositories=("o/r",),
        repository_roots={"o/r": str(work)},
        state_root=work / "state",
        workspace_root=work / "workspaces",
        poll_interval_seconds=300,
    )
    service.daemon(config, config_path)
    """
)


def _gone(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    # A zombie still answers kill(0); it is not running.
    state = subprocess.run(
        ["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True, check=False
    ).stdout.strip()
    return not state or state.startswith("Z")


def _command(pid: int) -> str:
    return subprocess.run(
        ["ps", "-o", "command=", "-p", str(pid)], capture_output=True, text=True, check=False
    ).stdout


def _wait_for(predicate, seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


def _receipt(work: Path) -> dict | None:
    try:
        return json.loads((work / "state" / "service" / "daemon.json").read_text())
    except (OSError, ValueError):
        return None


def _start_daemon(work: Path, mode: str) -> tuple[subprocess.Popen, Path, str]:
    """Start the daemon as launchd would (its own session); returns it, the helper pid file and
    the marker every helper process carries on its command line."""
    marker = f"3200.{uuid.uuid4().int % 10**6:06d}"
    pids = work / "helper.pids"
    helper = work / "helper.sh"
    # The helper leads its group (start_new_session); its own child stays in that group with
    # the output closed, and the helper keeps the pipes open until that child exits.
    helper.write_text(
        f'#!/bin/sh\nsleep {marker} >/dev/null 2>&1 &\necho "$$ $!" >> {pids}\nwait\n',
        encoding="utf-8",
    )
    helper.chmod(0o755)
    (work / "opencode").mkdir()
    (work / "artifact.json").write_text("{}", encoding="utf-8")
    (work / "config.json").write_text("{}", encoding="utf-8")
    (work / "driver.py").write_text(DRIVER, encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT), "PYTHONDONTWRITEBYTECODE": "1"}
    process = subprocess.Popen(
        [sys.executable, str(work / "driver.py"), str(work), str(helper), mode],
        cwd=REPO_ROOT,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    return process, pids, marker


def _stderr(process: subprocess.Popen) -> str:
    return process.stderr.read().decode() if process.stderr is not None else ""


def _helper_pids(pids: Path) -> list[int]:
    if not pids.exists():
        return []
    return [int(value) for line in pids.read_text().splitlines() for value in line.split()]


def _cleanup(process: subprocess.Popen, pids: Path, marker: str) -> None:
    """Never leave anything this test started; only pids still carrying its marker or helper
    path are signalled, so a pid reused by an unrelated process is left alone."""
    if process.poll() is None:
        process.kill()
        process.wait(timeout=10)
    for pid in _helper_pids(pids):
        if not _gone(pid) and (marker in _command(pid) or str(pids.parent) in _command(pid)):
            os.kill(pid, signal.SIGKILL)


def test_sigterm_during_a_poll_stops_every_helper_group_before_launchd_sigkill(tmp_path):
    process, pids, marker = _start_daemon(tmp_path, "helpers")
    try:
        # Both helpers (OpenCode and open-swe) and each one's own child are running.
        assert _wait_for(lambda: len(_helper_pids(pids)) == 4, 30), (
            _stderr(process) if process.poll() is not None else "helpers not started"
        )
        started = _helper_pids(pids)
        assert not any(_gone(pid) for pid in started)

        sent = time.monotonic()
        process.send_signal(signal.SIGTERM)
        process.wait(timeout=LAUNCHD_EXIT_TIMEOUT_SECONDS)
        elapsed = time.monotonic() - sent

        # Gone well inside the grace period, so launchd never needs its SIGKILL.
        assert elapsed < LAUNCHD_EXIT_TIMEOUT_SECONDS / 2, elapsed
        assert process.returncode == 0, _stderr(process)
        survivors = [pid for pid in started if not _wait_for(lambda pid=pid: _gone(pid), 5)]
        assert survivors == [], f"helper processes outlived the service: {survivors}"

        receipt = _receipt(tmp_path)
        assert receipt is not None
        assert receipt["status"] == "STOPPED"
        assert receipt["last_error"] == {
            "type": "ServiceInterrupted",
            "code": "SERVICE_INTERRUPTED",
        }
    finally:
        _cleanup(process, pids, marker)


def test_sigterm_between_polls_stops_without_recording_an_interruption(tmp_path):
    process, pids, marker = _start_daemon(tmp_path, "idle")
    try:
        assert _wait_for(lambda: (_receipt(tmp_path) or {}).get("successful_polls", 0) >= 1, 30), (
            _stderr(process) if process.poll() is not None else "no poll recorded"
        )
        process.send_signal(signal.SIGTERM)
        process.wait(timeout=LAUNCHD_EXIT_TIMEOUT_SECONDS)
        assert process.returncode == 0, _stderr(process)
        receipt = _receipt(tmp_path)
        assert receipt is not None
        assert (receipt["status"], receipt["last_error"]) == ("STOPPED", None)
    finally:
        _cleanup(process, pids, marker)
