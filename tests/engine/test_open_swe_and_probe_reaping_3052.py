"""#3052: the Open SWE runtime call and the gateway's assist/model-probe refresh kill the
provider's process group before they accept a result or release an Agy account lease.

Each case starts ONE grandchild through a Python double fork that stays in the child's process
group (no setsid) and records its pid in this test's own tmp dir. Cleanup signals only a pid
read from that pid file whose ``ps`` command line contains this test's unique tmp path, or the
process group of a child this test spawned itself while that child is unreaped. No pkill, no
pid-range scans, no real Agy lease (a tmp lock file and a fake manager), no gateway service.
"""

from __future__ import annotations

import fcntl
import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from nexus.core.argv_command import ProcessGroupReapingUnavailable
from nexus.orchestrator.unified_mcp_gateway_parts import assist_response
from nexus.orchestrator.unified_mcp_gateway_parts.assist_response import _AssistResponseMixin
from nexus.orchestrator.unified_mcp_gateway_parts.model_probe import _ModelProbeMixin
from nexus.services import open_swe_external_intelligence as osei
from nexus.services.agy_account_pool import AccountLeaseClaim

DOUBLE_FORK = r'''
import os, sys, time

def spawn_grandchild(pidfile, hold):
    """Double fork; the grandchild keeps the caller's pgid (no setsid)."""
    first = os.fork()
    if first:
        os.waitpid(first, 0)
        return
    if os.fork():
        os._exit(0)
    if not hold:
        null = os.open(os.devnull, os.O_RDWR)
        for fd in (0, 1, 2):
            os.dup2(null, fd)
    tmp = pidfile + ".tmp"
    with open(tmp, "w") as fh:
        fh.write(str(os.getpid()))
    os.replace(tmp, pidfile)
    time.sleep(60)
    os._exit(0)
'''


def _write(path: Path, text: str, *, executable: bool = False) -> Path:
    path.write_text(text, encoding="utf-8")
    if executable:
        path.chmod(0o755)
    return path


def _wait_pidfile(pidfile: Path, timeout: float = 10.0) -> int:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pidfile.exists():
            return int(pidfile.read_text())
        time.sleep(0.05)
    raise AssertionError(f"grandchild never wrote {pidfile}")


def _ps(pid: int, field: str) -> str:
    out = subprocess.run(
        ["ps", "-o", f"{field}=", "-p", str(pid)], capture_output=True, text=True, check=False
    )
    return out.stdout.strip()


def _ours_alive(pid: int, marker: str) -> bool:
    """Alive, not a zombie, and the command line names this test's own tmp path."""
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return marker in _ps(pid, "command") and not _ps(pid, "stat").startswith("Z")


def _gone_soon(pid: int, marker: str, seconds: float = 3.0) -> bool:
    deadline = time.monotonic() + seconds
    while _ours_alive(pid, marker) and time.monotonic() < deadline:
        time.sleep(0.05)
    return not _ours_alive(pid, marker)


@pytest.fixture
def box(tmp_path: Path):
    marker = str(tmp_path)
    pidfile = tmp_path / "grandchild.pid"
    try:
        yield tmp_path, pidfile, marker
    finally:
        if pidfile.exists():
            pid = int(pidfile.read_text())
            if _ours_alive(pid, marker):
                os.kill(pid, signal.SIGKILL)


# ---------------------------------------------------------------------------
# Open SWE runtime call (EIA daemon, Open SWE worker transport)
# ---------------------------------------------------------------------------


def _runtime_stub(tmp: Path, pidfile: Path, hold: bool) -> Path:
    body = (
        f"#!{sys.executable}\n"
        + DOUBLE_FORK
        + f"""
import json
request = json.loads(sys.stdin.read())
spawn_grandchild({str(pidfile)!r}, {hold!r})
sys.stdout.write(json.dumps({{"schema": {osei.PROTOCOL_RESULT_SCHEMA!r}, "kind": "semantic",
                              "echo": request["operation"]}}) + "\\n")
sys.stdout.flush()
"""
    )
    return _write(tmp / "open_swe_runtime_stub.py", body, executable=True)


def test_open_swe_runtime_call_kills_group_after_normal_exit(box):
    tmp, pidfile, marker = box
    exe = _runtime_stub(tmp, pidfile, hold=False)
    value, _stderr, started, failure = osei._runtime_call(
        str(exe), {"operation": "semantic_run"}, provider_id="none", timeout=10.0
    )
    pid = _wait_pidfile(pidfile)
    assert started and failure == "" and value is not None, (failure, value)
    # The payload still reaches the runtime on stdin.
    assert value["echo"] == "semantic_run"
    assert not _ours_alive(pid, marker), (
        f"grandchild {pid} (pgid {_ps(pid, 'pgid')}) still alive after _runtime_call "
        "returned a successful result"
    )


def test_open_swe_runtime_call_timeout_kills_in_group_holder(box):
    """A grandchild holding stdout forces the timeout path; the group escalation reaches it and
    the call returns within its bounds."""
    tmp, pidfile, marker = box
    exe = _runtime_stub(tmp, pidfile, hold=True)
    started_at = time.monotonic()
    value, _stderr, started, failure = osei._runtime_call(
        str(exe), {"operation": "semantic_run"}, provider_id="none", timeout=3.0
    )
    elapsed = time.monotonic() - started_at
    pid = _wait_pidfile(pidfile)
    assert value is None and failure == "runtime_timeout" and started
    assert elapsed < 8.0, elapsed
    assert _gone_soon(pid, marker)


def test_open_swe_runtime_call_refused_spawns_nothing(monkeypatch, tmp_path):
    def refuse():
        raise ProcessGroupReapingUnavailable(22, "SIGCHLD is not SIG_DFL")

    def no_popen(*args, **kwargs):
        raise AssertionError("nothing may be spawned")

    monkeypatch.setattr(osei, "require_child_stays_unreaped", refuse)
    monkeypatch.setattr(osei.subprocess, "Popen", no_popen)
    assert osei._runtime_call(
        str(tmp_path / "runtime"), {"operation": "semantic_run"}, provider_id="none", timeout=1.0
    ) == (None, "", False, "runtime_reaping_unavailable")


# ---------------------------------------------------------------------------
# Gateway assist / model-probe refresh and the Agy account lease
# Stubbed object: no gateway instance, no real pool, no real lease.
# ---------------------------------------------------------------------------


class _FakeManager:
    def __init__(self) -> None:
        self.released: list[object] = []

    def release(self, lease) -> None:
        self.released.append(lease)


class _StubGateway(_AssistResponseMixin):
    _release_assist_account_claim = _ModelProbeMixin._release_assist_account_claim
    _abandon_assist_account_claim = _ModelProbeMixin._abandon_assist_account_claim

    def __init__(self, job, process, claim) -> None:
        self._job = job
        self._assist_lock = threading.RLock()
        self._assist_processes = {job["task_id"]: process}
        self._assist_account_claims = {job["task_id"]: claim}

    def _assist_read(self, task_id):
        return dict(self._job)

    def _assist_write(self, job):
        self._job = dict(job)
        return dict(job)

    @staticmethod
    def _utc_now():
        return "2026-11-01T00:00:00+00:00"

    @staticmethod
    def _assist_record_stream_artifacts(job):
        return None

    def _decode_model_probe_payload(self, stdout, provider, model):
        return None, None

    def _validate_output_schema(self, parsed, schema):
        return False, "stub"

    def _write_probe_evidence(self, job):
        return None


def _lease(tmp: Path):
    lock_path = tmp / "account.lock"
    receipt_path = tmp / "account.receipt.json"
    receipt_path.write_text("{}")
    lock_obj = open(lock_path, "a+")  # noqa: SIM115 - owned by the claim
    fcntl.flock(lock_obj.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    manager = _FakeManager()
    claim = AccountLeaseClaim(
        lease=object(),
        lock_file_obj=lock_obj,
        lock_path=lock_path,
        receipt_path=receipt_path,
        account_alias_hash="alias",
        lease_id_hash="lease",
        manager=manager,
        internal_id="stub",
    )
    return claim, manager, lock_path, receipt_path


def _lock_free(lock_path: Path) -> bool:
    with open(lock_path, "a+") as other:
        try:
            fcntl.flock(other.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        fcntl.flock(other.fileno(), fcntl.LOCK_UN)
        return True


def _launch_provider(tmp: Path, pidfile: Path, claim, *, linger: float = 0.0):
    """Launch like model_probe.py does: new session, the lease fd passed to the provider."""
    provider = _write(
        tmp / "agy_provider_stub.py",
        f"#!{sys.executable}\n"
        + DOUBLE_FORK
        + f"\nspawn_grandchild({str(pidfile)!r}, False)\ntime.sleep({linger!r})\nprint('done')\n",
        executable=True,
    )
    stdout_path, stderr_path = tmp / "out.txt", tmp / "err.txt"
    with open(stdout_path, "w") as out, open(stderr_path, "w") as err:
        process = subprocess.Popen(
            [str(provider)],
            stdout=out,
            stderr=err,
            text=True,
            start_new_session=True,
            pass_fds=(claim.lock_file_obj.fileno(),),
        )
    job = {
        "task_id": "t1",
        "status": "RUNNING",
        "job_kind": "model_probe",
        "provider": "agy",
        "pid": process.pid,
        "pgid": process.pid,
        "stdout_artifact": str(stdout_path),
        "stderr_artifact": str(stderr_path),
        "account_lease_id_hash": "lease",
        "workspace_root": str(tmp / "no-such-probe-workspace"),
        "resolved_model": "stub",
        "started_at": "2026-11-01T00:00:00+00:00",
    }
    return process, job


def _wait_exit_unreaped(process: subprocess.Popen, timeout: float = 10.0) -> None:
    """Wait for the provider to exit without reaping it (as the gateway would find it)."""
    deadline = time.monotonic() + timeout
    while os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOWAIT | os.WNOHANG) is None:
        assert time.monotonic() < deadline, "provider stub did not exit"
        time.sleep(0.02)


def _kill_own_group(process: subprocess.Popen) -> None:
    """Test cleanup: SIGKILL the group of a child this test spawned, only while unreaped."""
    if process.returncode is None:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except OSError:
            pass
        process.wait(timeout=5)


def test_model_probe_lease_released_only_after_group_killed(box):
    tmp, pidfile, marker = box
    claim, manager, lock_path, receipt_path = _lease(tmp)
    process, job = _launch_provider(tmp, pidfile, claim)
    try:
        pid = _wait_pidfile(pidfile)
        _wait_exit_unreaped(process)
        refreshed = _StubGateway(job, process, claim)._assist_refresh("t1")
    finally:
        _kill_own_group(process)
    assert refreshed["status"] in {"FAILED", "COMPLETED"}, refreshed
    assert refreshed["account_lease_cleanup_status"] == "RELEASED"
    assert manager.released and not receipt_path.exists() and _lock_free(lock_path)
    assert not _ours_alive(pid, marker), (
        f"grandchild {pid} (pgid {_ps(pid, 'pgid')}) still alive after the gateway released "
        "the Agy account lease (lock free, receipt removed, manager released)"
    )


def test_model_probe_lease_kept_when_group_cleanup_unprovable(box):
    """The provider was reaped outside the refresh: its group can no longer be signalled safely,
    so the lease is abandoned (not released) and the job needs reconciliation."""
    tmp, pidfile, marker = box
    claim, manager, lock_path, receipt_path = _lease(tmp)
    process, job = _launch_provider(tmp, pidfile, claim)
    workspace = tmp / "probe-workspace"
    workspace.mkdir()
    job["workspace_root"] = str(workspace)
    pid = _wait_pidfile(pidfile)
    process.wait(timeout=10)
    refreshed = _StubGateway(job, process, claim)._assist_refresh("t1")
    assert refreshed["status"] == "UNKNOWN_REQUIRES_RECONCILE", refreshed
    assert refreshed["blocker"] == "ASSIST_PROVIDER_GROUP_CLEANUP_INCOMPLETE"
    assert refreshed["reconciliation_required"] is True
    assert refreshed["account_lease_cleanup_status"] == "RECONCILIATION_REQUIRED"
    assert not manager.released and receipt_path.exists()
    # The grandchild still holds the inherited lease fd, so the account stays locked.
    assert _ours_alive(pid, marker) and not _lock_free(lock_path)
    assert workspace.exists(), "workspace removed while a provider descendant may still use it"


def test_model_probe_past_deadline_group_killed_then_lease_released(box):
    tmp, pidfile, marker = box
    claim, manager, lock_path, receipt_path = _lease(tmp)
    process, job = _launch_provider(tmp, pidfile, claim, linger=60.0)
    try:
        pid = _wait_pidfile(pidfile)
        job["started_at"] = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(time.time() - 5))
        gateway = _StubGateway(job, process, claim)
        running = gateway._assist_refresh("t1")
        assert running["status"] == "RUNNING" and not manager.released
        assert _ours_alive(pid, marker)
        gateway._job["started_at"] = "2020-01-01T00:00:00+00:00"
        refreshed = gateway._assist_refresh("t1")
    finally:
        _kill_own_group(process)
    assert refreshed["status"] == "FAILED", refreshed
    assert refreshed["blocker"] == "ASSIST_PROVIDER_DEADLINE_EXCEEDED"
    assert refreshed["model_response_verified"] is False
    assert refreshed["account_lease_cleanup_status"] == "RELEASED"
    assert manager.released and _lock_free(lock_path)
    assert not _ours_alive(pid, marker)
    assert process.returncode == -signal.SIGKILL


def test_open_swe_runtime_result_json_still_parsed(box):
    """Binary pipes: a UTF-8 result with non-ASCII text decodes as before."""
    tmp, _pidfile, _marker = box
    exe = _write(
        tmp / "plain_runtime.py",
        f"#!{sys.executable}\nimport json, sys\nsys.stdin.read()\n"
        f"print(json.dumps({{'schema': {osei.PROTOCOL_RESULT_SCHEMA!r}, 'kind': 'semantic',"
        " 'raw': '\\u7d50\\u679c'}, ensure_ascii=False))\n",
        executable=True,
    )
    value, _stderr, started, failure = osei._runtime_call(
        str(exe), {"operation": "semantic_run"}, provider_id="none", timeout=10.0
    )
    assert started and failure == ""
    assert value is not None and value["raw"] == json.loads('"\\u7d50\\u679c"')


def test_second_refresh_of_a_settled_provider_sees_a_clean_exit(box):
    """Concurrent refreshes of one job: the one that did not kill and reap the group must not
    take the reap for one done elsewhere (which would abandon the lease)."""
    tmp, pidfile, marker = box
    claim, _manager, _lock_path, _receipt_path = _lease(tmp)
    process, job = _launch_provider(tmp, pidfile, claim)
    try:
        pid = _wait_pidfile(pidfile)
        _wait_exit_unreaped(process)
        assert assist_response._settle_provider_group(job, process) == (True, True, False)
        assert assist_response._settle_provider_group(job, process) == (True, True, False)
    finally:
        _kill_own_group(process)
        claim.release()
    assert not _ours_alive(pid, marker)
