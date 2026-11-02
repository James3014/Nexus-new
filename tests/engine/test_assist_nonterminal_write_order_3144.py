"""#3144 item 1: once a cancel, query or reconcile has held an assist job for reconciliation
(UNKNOWN_REQUIRES_RECONCILE, or ``reconciliation_required``), a query's RUNNING heartbeat from a
read made before that does not put the record back to RUNNING. Held and settling writes still
land, and so does a query's final outcome over a concurrent query's heartbeat (#3139).

Every test runs with its cwd in a sentinel directory under tmp_path and the assist workspace
parent pointed at tmp_path; each asserts the sentinel survives. No real provider runs: the
provider is a stand-in whose pid is above any pid_max (Linux 2**22, macOS 99999), and
``os.kill``, ``os.killpg``, the group listing, the group settle step and the group termination
are replaced, so nothing is signalled on the host. No live gateway, no Agy, no real lease.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from nexus.core import argv_command
from nexus.orchestrator.unified_mcp_gateway import UnifiedMCPGateway
from nexus.orchestrator.unified_mcp_gateway_parts import assist_jobs, assist_response
from tests.nexus.orchestrator.test_unified_mcp_gateway import FakeService

# Above Linux's largest pid_max (2**22) and macOS's (99999): never a real process.
FAKE_PID = 2**22 + 3144
TASK = "t3144-order"
JOB_ID = "assist-3144-order"


class _FakeProvider:
    """A provider Popen stand-in that never exits; nothing real behind its pid."""

    def __init__(self) -> None:
        self.pid = FAKE_PID
        self.returncode = None

    def wait(self, timeout=None):
        raise AssertionError("the test provider is never waited on")

    def poll(self):
        raise AssertionError("the test provider is never polled")


class _Host:
    """os.kill / os.killpg / the group listing for the fake provider: the leader and a group
    member are alive; signals are recorded, never sent."""

    def __init__(self) -> None:
        self.sent: list[int] = []

    def kill(self, pid: int, sig: int) -> None:
        assert pid == FAKE_PID, f"os.kill on a pid this test does not own: {pid}"
        if sig != 0:
            self.sent.append(sig)

    def killpg(self, pgid: int, sig: int) -> None:
        assert pgid == FAKE_PID, f"os.killpg on a group this test does not own: {pgid}"
        self.sent.append(sig)

    def live_members(self, pgid: int) -> list[int]:
        assert pgid == FAKE_PID, f"listing a group this test does not own: {pgid}"
        return [FAKE_PID + 1]


class _LockWithEntryHook:
    """The gateway's assist lock, calling ``hook()`` before each entry."""

    def __init__(self, lock, hook) -> None:
        self._lock = lock
        self._hook = hook

    def __enter__(self):
        self._hook()
        return self._lock.__enter__()

    def __exit__(self, *exc):
        return self._lock.__exit__(*exc)

    def acquire(self, *args, **kwargs):
        return self._lock.acquire(*args, **kwargs)

    def release(self):
        return self._lock.release()


@pytest.fixture
def box(tmp_path, monkeypatch):
    """cwd = a sentinel directory under tmp_path; assist workspace parent = tmp_path/assist-root;
    every host-facing call of the provider's group is a stand-in."""
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    sentinel = cwd / "SENTINEL"
    sentinel.write_text("keep", encoding="utf-8")
    root = tmp_path / "assist-root"
    root.mkdir()
    state = tmp_path / "state"
    state.mkdir()
    monkeypatch.chdir(cwd)
    monkeypatch.setattr(assist_response, "ASSIST_WORKSPACE_PARENT", str(root), raising=False)
    host = _Host()
    monkeypatch.setattr(os, "kill", host.kill)
    monkeypatch.setattr(os, "killpg", host.killpg)
    monkeypatch.setattr(argv_command, "_live_group_members", host.live_members)
    # The provider never exits, and its group is never signalled or reaped for real.
    monkeypatch.setattr(assist_response, "kill_group_if_exited", lambda process: False)
    terminated: list = []

    def terminate(process) -> bool:
        assert process.pid == FAKE_PID
        terminated.append(process)
        return False  # a group member outlived SIGTERM and SIGKILL

    monkeypatch.setattr(assist_jobs, "_terminate_provider_group", terminate)
    service = FakeService()
    service.state_dir = state
    gateway = UnifiedMCPGateway(service=service)
    yield SimpleNamespace(
        tmp=tmp_path,
        sentinel=sentinel,
        root=root,
        state=state,
        gateway=gateway,
        host=host,
        terminated=terminated,
    )
    assert sentinel.exists(), "the test's cwd lost its sentinel file"
    assert host.sent == [], f"a signal reached the host stand-in: {host.sent}"


def _job(box, workspace_root: str, **fields) -> dict:
    job = {
        "schema": "nexus.assisted_provider_job.v1",
        "task_id": TASK,
        "job_id": JOB_ID,
        "job_kind": "assist",
        "status": "RUNNING",
        "provider": "cline",
        "pid": FAKE_PID,
        "pgid": FAKE_PID,
        "workspace_mode": "isolated",
        "workspace_root": workspace_root,
        "filesystem_before": {},
        "stdout_artifact": str(box.state / "out.txt"),
        "stderr_artifact": str(box.state / "err.txt"),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "attempt_history": [],
    }
    job.update(fields)
    return job


def _running_job(box) -> Path:
    """A running job whose provider this gateway holds unreaped."""
    workspace = box.root / "nexus-assist-t3144-order-abc"
    workspace.mkdir()
    (workspace / "partial.txt").write_text("partial", encoding="utf-8")
    box.gateway._assist_write(_job(box, str(workspace)))
    box.gateway._assist_processes[TASK] = _FakeProvider()
    return workspace


def _before_heartbeat_write(box, monkeypatch, other) -> dict:
    """Just before the query's RUNNING heartbeat write takes the assist lock, ``other()`` runs
    once (another call of the same job); its return value is kept under "other"."""
    state: dict = {}

    def hook() -> None:
        # hook <- __enter__ <- _assist_write_current <- _assist_refresh
        if "other" in state or sys._getframe(2).f_code.co_name != "_assist_write_current":
            return
        if sys._getframe(3).f_code.co_name != "_assist_refresh":
            return
        state["other"] = None
        state["other"] = other()

    monkeypatch.setattr(
        box.gateway, "_assist_lock", _LockWithEntryHook(box.gateway._assist_lock, hook)
    )
    return state


def _assert_held(record: dict, blocker: str) -> None:
    assert (record["job_id"], record["status"], record["blocker"]) == (
        JOB_ID,
        "UNKNOWN_REQUIRES_RECONCILE",
        blocker,
    ), record
    assert record["reconciliation_required"] is True, record


# ---------------------------------------------------------------------------
# A stale heartbeat does not put a held job back to RUNNING
# ---------------------------------------------------------------------------


def test_query_heartbeat_keeps_a_job_a_cancel_held_after_the_query_read(box, monkeypatch):
    """The cancel cannot end the provider's group and holds the job for reconciliation; the
    query read the job as RUNNING before that and found the provider still running."""
    workspace = _running_job(box)
    state = _before_heartbeat_write(box, monkeypatch, lambda: box.gateway._assist_cancel(TASK))
    result = box.gateway._assist_refresh(TASK)
    assert state.get("other") is not None, "the query wrote its heartbeat without the lock hook"
    _assert_held(state["other"], "ASSIST_CANCEL_CLEANUP_INCOMPLETE")
    record = box.gateway._assist_read(TASK)
    assert record is not None
    _assert_held(record, "ASSIST_CANCEL_CLEANUP_INCOMPLETE")
    assert result is not None
    _assert_held(result, "ASSIST_CANCEL_CLEANUP_INCOMPLETE")
    assert len(box.terminated) == 1
    assert TASK not in box.gateway._assist_processes
    # The provider's group may still use the workspace: kept.
    assert (workspace / "partial.txt").exists()


def test_after_the_stale_heartbeat_the_task_still_reports_reconciliation(box, monkeypatch):
    """While the provider's leader is alive, a later query and a reconcile report the job as
    needing reconciliation, not as RUNNING."""
    workspace = _running_job(box)
    _before_heartbeat_write(box, monkeypatch, lambda: box.gateway._assist_cancel(TASK))
    box.gateway._assist_refresh(TASK)
    waited = box.gateway._assist_wait(TASK, timeout_seconds=0.0)
    assert waited["status"] == "UNKNOWN_REQUIRES_RECONCILE", waited
    reconciled = box.gateway._task_reconcile({"task_id": TASK})
    assert reconciled["status"] == "UNKNOWN_REQUIRES_RECONCILE", reconciled
    record = box.gateway._assist_read(TASK)
    assert record is not None
    assert (record["status"], record["reconciliation_required"]) == (
        "UNKNOWN_REQUIRES_RECONCILE",
        True,
    ), record
    assert (workspace / "partial.txt").exists()


def test_query_heartbeat_keeps_a_job_another_query_held_after_its_read(box, monkeypatch):
    """Another query found the provider exited with its group not clean and held the job."""
    _running_job(box)

    def hold():
        read = box.gateway._assist_read(TASK)
        assert read is not None
        return box.gateway._assist_hold_for_group(TASK, dict(read), 0)

    state = _before_heartbeat_write(box, monkeypatch, hold)
    result = box.gateway._assist_refresh(TASK)
    assert state.get("other") is not None, "the query wrote its heartbeat without the lock hook"
    record = box.gateway._assist_read(TASK)
    assert record is not None
    _assert_held(record, "ASSIST_PROVIDER_GROUP_CLEANUP_INCOMPLETE")
    assert result is not None
    _assert_held(result, "ASSIST_PROVIDER_GROUP_CLEANUP_INCOMPLETE")


def test_query_of_a_held_job_with_no_provider_keeps_it_held(box):
    """A cancel of a job with an account lease and no started provider holds it for
    reconciliation; a later query finds no provider and no pid and must not report RUNNING."""
    box.gateway._assist_write(
        _job(
            box,
            "",
            pid=None,
            pgid=None,
            status="UNKNOWN_REQUIRES_RECONCILE",
            blocker="ASSIST_CANCEL_CLEANUP_INCOMPLETE",
            reconciliation_required=True,
            account_lease_id_hash="lease-3144",
            account_lease_released=False,
            account_lease_cleanup_status="RECONCILIATION_REQUIRED",
        )
    )
    result = box.gateway._assist_refresh(TASK)
    assert result is not None
    _assert_held(result, "ASSIST_CANCEL_CLEANUP_INCOMPLETE")
    record = box.gateway._assist_read(TASK)
    assert record is not None
    _assert_held(record, "ASSIST_CANCEL_CLEANUP_INCOMPLETE")


def test_query_heartbeat_still_lands_over_a_running_record(box):
    """Control: a query of a running job still records its heartbeat."""
    _running_job(box)
    result = box.gateway._assist_refresh(TASK)
    assert result is not None and result["status"] == "RUNNING", result
    record = box.gateway._assist_read(TASK)
    assert record is not None
    assert record["status"] == "RUNNING" and record.get("last_polled_at"), record


# ---------------------------------------------------------------------------
# Transition table over ``_assist_write_current`` (same job id)
# ---------------------------------------------------------------------------

_RUNNING = {"status": "RUNNING", "blocker": None, "reconciliation_required": False}
_SUBMITTED = {"status": "SUBMITTED", "blocker": None, "reconciliation_required": False}
_HELD_BY_CANCEL = {
    "status": "UNKNOWN_REQUIRES_RECONCILE",
    "blocker": "ASSIST_CANCEL_CLEANUP_INCOMPLETE",
    "reconciliation_required": True,
}
_HELD_BY_QUERY = {
    "status": "UNKNOWN_REQUIRES_RECONCILE",
    "blocker": "ASSIST_PROVIDER_GROUP_CLEANUP_INCOMPLETE",
    "reconciliation_required": True,
}
_PROCESS_LOST = {
    "status": "UNKNOWN_REQUIRES_RECONCILE",
    "blocker": "ASSIST_PROVIDER_PROCESS_LOST",
    "reconciliation_required": True,
}
_UNKNOWN_UNFLAGGED = {
    "status": "UNKNOWN_REQUIRES_RECONCILE",
    "blocker": "ASSIST_CANCEL_CLEANUP_INCOMPLETE",
    "reconciliation_required": False,
}
# A cancel of a held job whose workspace was removable: CANCELLED, still to be reconciled.
_CANCELLED_PENDING = {
    "status": "CANCELLED",
    "blocker": "ASSIST_PROVIDER_PROCESS_LOST",
    "reconciliation_required": True,
}
_LEASE_PRESERVED = {
    "status": "UNKNOWN_REQUIRES_RECONCILE",
    "blocker": "ASSIST_ACCOUNT_LEASE_RECONCILIATION_REQUIRED",
    "reconciliation_required": True,
}
_RECONCILED = {
    "status": "FAILED",
    "blocker": "ASSIST_PROVIDER_PROCESS_LOST",
    "reconciliation_required": False,
}
_CANCELLED = {
    "status": "CANCELLED",
    "blocker": "ASSIST_CANCELLED",
    "reconciliation_required": False,
}
_COMPLETED = {"status": "COMPLETED", "blocker": None, "reconciliation_required": False}
# Written before #3154 by a call that flagged the job without changing its status.
_FLAGGED_RUNNING = {**_RUNNING, "reconciliation_required": True}

# (record on disk, record written, whether the write lands)
_TRANSITIONS = [
    # Refused: a live write over a held record (#3144).
    pytest.param(_HELD_BY_CANCEL, _RUNNING, False, id="held-by-cancel-not-running"),
    pytest.param(_HELD_BY_QUERY, _RUNNING, False, id="held-by-query-not-running"),
    pytest.param(_PROCESS_LOST, _RUNNING, False, id="process-lost-not-running"),
    pytest.param(_UNKNOWN_UNFLAGGED, _RUNNING, False, id="unknown-unflagged-not-running"),
    pytest.param(_CANCELLED_PENDING, _RUNNING, False, id="pending-cancel-not-running"),
    pytest.param(_HELD_BY_CANCEL, _SUBMITTED, False, id="held-not-submitted"),
    pytest.param(
        _HELD_BY_CANCEL,
        {**_RUNNING, "reconciliation_required": True},
        False,
        id="held-not-running-even-flagged",
    ),
    # Old data: a RUNNING record that carries the reconciliation flag is held as well.
    pytest.param(_FLAGGED_RUNNING, _RUNNING, False, id="flagged-running-not-running"),
    pytest.param(_FLAGGED_RUNNING, _SUBMITTED, False, id="flagged-running-not-submitted"),
    # Lands: live -> live (heartbeats; a submit's record before its first query).
    pytest.param(_SUBMITTED, _RUNNING, True, id="submitted-running"),
    pytest.param(_RUNNING, _RUNNING, True, id="running-heartbeat"),
    # Lands: live -> held (hold for the group, process lost, cancel cleanup incomplete).
    pytest.param(_RUNNING, _HELD_BY_QUERY, True, id="running-held-by-query"),
    pytest.param(_RUNNING, _PROCESS_LOST, True, id="running-process-lost"),
    pytest.param(_RUNNING, _HELD_BY_CANCEL, True, id="running-held-by-cancel"),
    # Lands: held -> held (reconcile keeps waiting for the group or the lease).
    pytest.param(_HELD_BY_QUERY, _HELD_BY_QUERY, True, id="held-reconcile-waits"),
    pytest.param(_HELD_BY_QUERY, _LEASE_PRESERVED, True, id="held-lease-preserved"),
    pytest.param(_HELD_BY_CANCEL, _PROCESS_LOST, True, id="held-by-cancel-process-lost"),
    pytest.param(_HELD_BY_QUERY, _CANCELLED_PENDING, True, id="held-cancel-pending"),
    # Lands: held -> settled (reconcile, cancel, a query finishing after a lease reconcile).
    pytest.param(_HELD_BY_QUERY, _RECONCILED, True, id="held-reconciled"),
    pytest.param(_CANCELLED_PENDING, _RECONCILED, True, id="pending-cancel-reconciled"),
    pytest.param(_PROCESS_LOST, _CANCELLED, True, id="held-cancelled"),
    pytest.param(_LEASE_PRESERVED, _COMPLETED, True, id="lease-reconciled-completed"),
    pytest.param(_FLAGGED_RUNNING, _RECONCILED, True, id="flagged-running-reconciled"),
    pytest.param(_FLAGGED_RUNNING, _HELD_BY_CANCEL, True, id="flagged-running-held-by-cancel"),
    # Lands: a query's final outcome over a concurrent query's heartbeat (#3139).
    pytest.param(_RUNNING, _COMPLETED, True, id="running-completed"),
    pytest.param(_RUNNING, _CANCELLED, True, id="running-cancelled"),
]


@pytest.mark.parametrize(("on_disk", "written", "lands"), _TRANSITIONS)
def test_record_write_of_the_same_job_between_unsettled_states(box, on_disk, written, lands):
    stored = box.gateway._assist_write(_job(box, "", **on_disk))
    job = _job(box, "", **written)
    result = box.gateway._assist_write_current(TASK, job)
    record = box.gateway._assist_read(TASK)
    assert record is not None
    expected = {**stored, **written} if lands else stored
    for key in ("status", "blocker", "reconciliation_required"):
        assert record.get(key) == expected.get(key), (key, record)
        assert result.get(key) == expected.get(key), (key, result)


# ---------------------------------------------------------------------------
# A query finishing the job: its side effects come before its final write, and the provider
# stays registered until that write (#3144)
# ---------------------------------------------------------------------------

_PATCH = "diff --git a/x.txt b/x.txt\n--- a/x.txt\n+++ b/x.txt\n@@ -1 +1 @@\n-a\n+b\n"


class _Claim:
    """An Agy account claim stand-in that counts its releases; no real lease behind it. Its
    ``lease_id_hash`` is the lease of the #3160 tests below."""

    def __init__(self, lease_id_hash: str = "lease-3160") -> None:
        self.releases = 0
        self.lease_id_hash = lease_id_hash

    def release(self) -> None:
        self.releases += 1

    def abandon_parent_reference(self) -> None:
        raise AssertionError("the claim was abandoned instead of released")


def _provider_exited(box, monkeypatch) -> None:
    """The registered provider exited with 0 and its group is empty: the settle step finds it
    exited (it is never reaped for real), the leader's pid is gone, the group listing is empty,
    and its output decodes as a substantive patch."""

    def exited(process) -> bool:
        assert process.pid == FAKE_PID
        process.returncode = 0
        return True

    def kill(pid: int, sig: int) -> None:
        assert pid == FAKE_PID, f"os.kill on a pid this test does not own: {pid}"
        if sig == 0:
            raise ProcessLookupError(pid)
        box.host.sent.append(sig)

    def live_members(pgid: int) -> list[int]:
        assert pgid == FAKE_PID, f"listing a group this test does not own: {pgid}"
        return []

    monkeypatch.setattr(assist_response, "kill_group_if_exited", exited)
    monkeypatch.setattr(os, "kill", kill)
    monkeypatch.setattr(argv_command, "_live_group_members", live_members)
    monkeypatch.setattr(
        box.gateway,
        "_decode_assist_payload",
        lambda stdout, provider, *, require_patch=False: {"patch": _PATCH},
    )
    monkeypatch.setattr(box.gateway, "_assist_patch_is_substantive", lambda patch: True)


def _before_final_write(box, monkeypatch, other) -> dict:
    """``other()`` runs once in the query's probe-evidence step: after its lease release and
    workspace removal, before its final write. Its return value is kept under "other"."""
    state: dict = {}
    write_probe_evidence = box.gateway._write_probe_evidence

    def evidence(job):
        if "other" not in state:
            state["other"] = None
            state["other"] = other()
        return write_probe_evidence(job)

    monkeypatch.setattr(box.gateway, "_write_probe_evidence", evidence)
    return state


def _assert_completed(record: dict) -> None:
    assert (record["job_id"], record["status"], record["blocker"]) == (
        JOB_ID,
        "COMPLETED",
        None,
    ), record
    assert record["result"] == {"patch": _PATCH}, record
    assert record["exit_code"] == 0, record
    assert not record.get("reconciliation_required"), record


def test_cancel_while_a_query_finishes_the_job_keeps_the_provider_outcome(box, monkeypatch):
    """The cancel runs after the query removed the workspace and before it wrote the outcome:
    it must find the provider still registered, not a lost process it would settle CANCELLED
    over the provider's own result."""
    workspace = _running_job(box)
    _provider_exited(box, monkeypatch)
    state = _before_final_write(box, monkeypatch, lambda: box.gateway._assist_cancel(TASK))
    result = box.gateway._assist_refresh(TASK)
    assert state.get("other") is not None, "the cancel never ran before the final write"
    assert (state["other"]["status"], state["other"]["blocker"]) == ("COMPLETED", None), state
    record = box.gateway._assist_read(TASK)
    assert record is not None
    _assert_completed(record)
    assert result is not None
    _assert_completed(result)
    assert box.terminated == []
    assert TASK not in box.gateway._assist_processes
    assert not workspace.exists()


def test_query_while_another_query_finishes_the_job_does_not_report_a_lost_process(
    box, monkeypatch
):
    workspace = _running_job(box)
    _provider_exited(box, monkeypatch)
    state = _before_final_write(
        box, monkeypatch, lambda: box.gateway._assist_wait(TASK, timeout_seconds=0.0)
    )
    box.gateway._assist_refresh(TASK)
    assert state.get("other") is not None, "the second query never ran before the final write"
    assert (state["other"]["status"], state["other"]["blocker"]) == ("COMPLETED", None), state
    record = box.gateway._assist_read(TASK)
    assert record is not None
    _assert_completed(record)
    assert TASK not in box.gateway._assist_processes
    assert not workspace.exists()


def test_query_whose_final_write_is_refused_released_the_lease_once_and_records_it(
    box, monkeypatch
):
    """Pins the order of the query's side effects: a cancel settled the job CANCELLED after
    the query took and released the account claim (the cancel found it gone), so the query's
    final write is refused. The query still released the claim, exactly once, the kept record
    shows the release, the workspace is removed and the provider is unregistered; a later
    cancel releases nothing."""
    workspace = _running_job(box)
    _provider_exited(box, monkeypatch)
    record = box.gateway._assist_read(TASK)
    assert record is not None
    record.update({"account_lease_id_hash": "lease-3144", "account_lease_released": False})
    box.gateway._assist_write(record)
    claim = _Claim()
    box.gateway._assist_account_claims[TASK] = claim

    def cancel_settles() -> dict:
        settled = box.gateway._assist_read(TASK)
        assert settled is not None
        settled.update({
            "status": "CANCELLED",
            "blocker": "ASSIST_CANCELLED",
            "reconciliation_required": False,
            "process_killed": True,
            "account_lease_released": False,
            "account_lease_cleanup_status": "RECONCILIATION_REQUIRED",
        })
        return box.gateway._assist_write(settled)

    state = _before_final_write(box, monkeypatch, cancel_settles)
    result = box.gateway._assist_refresh(TASK)
    assert state.get("other") is not None, "the cancel never settled before the final write"
    assert claim.releases == 1, claim.releases
    record = box.gateway._assist_read(TASK)
    assert record is not None
    assert (record["status"], record["blocker"]) == ("CANCELLED", "ASSIST_CANCELLED"), record
    assert (record["account_lease_released"], record["account_lease_cleanup_status"]) == (
        True,
        "RELEASED",
    ), record
    assert result == record
    assert TASK not in box.gateway._assist_processes
    assert not workspace.exists()
    box.gateway._assist_cancel(TASK)
    assert claim.releases == 1, claim.releases


# ---------------------------------------------------------------------------
# #3160: a model probe holding an Agy account lease. A second call of the same job between the
# finishing query's lease release and its final write finds the release done by this job, not
# a lost claim: it answers the job's real state and records nothing the final write overwrites.
# ---------------------------------------------------------------------------

LEASE = "lease-3160"
_PROBE_RESULT = {"answer": "ok"}


def _lease_probe_finishing(box, monkeypatch) -> tuple[Path, _Claim]:
    """A running Agy model probe that holds an account claim; its provider exited with 0 and
    its output decodes as a verified probe answer. Nothing real: no Popen, no lease, and
    ``os.kill``/``os.killpg`` raise on any real signal."""
    workspace = _running_job(box)
    _provider_exited(box, monkeypatch)

    def kill(pid: int, sig: int) -> None:
        assert pid == FAKE_PID, f"os.kill on a pid this test does not own: {pid}"
        if sig != 0:
            raise AssertionError(f"os.kill with a real signal: {sig}")
        raise ProcessLookupError(pid)

    def killpg(pgid: int, sig: int) -> None:
        raise AssertionError(f"os.killpg({pgid}, {sig}) in a test that signals nothing")

    def popen(*args, **kwargs):
        raise AssertionError("a provider was launched")

    monkeypatch.setattr(os, "kill", kill)
    monkeypatch.setattr(os, "killpg", killpg)
    monkeypatch.setattr(subprocess, "Popen", popen)
    monkeypatch.setattr(
        box.gateway,
        "_decode_model_probe_payload",
        lambda stdout, provider, model: (dict(_PROBE_RESULT), "provider_stdout"),
    )
    record = box.gateway._assist_read(TASK)
    assert record is not None
    record.update({
        "job_kind": "model_probe",
        "provider": "agy",
        "resolved_model": "gemini-test",
        "account_alias_hash": "alias-3160",
        "account_lease_id_hash": LEASE,
        "account_lease_released": False,
        "account_lease_cleanup_status": "HELD",
    })
    box.gateway._assist_write(record)
    claim = _Claim()
    box.gateway._assist_account_claims[TASK] = claim
    return workspace, claim


def _assert_probe_completed(record: dict) -> None:
    assert (record["job_id"], record["status"], record["blocker"]) == (
        JOB_ID,
        "COMPLETED",
        None,
    ), record
    assert record["result"] == _PROBE_RESULT, record
    assert record["model_response_verified"] is True, record
    assert not record.get("reconciliation_required"), record
    assert (record["account_lease_released"], record["account_lease_cleanup_status"]) == (
        True,
        "RELEASED",
    ), record


def _in_window(box, call) -> dict:
    """Run ``call()`` and keep its answer and the record it left on disk."""
    answer = call()
    record = box.gateway._assist_read(TASK)
    assert record is not None
    return {"answer": answer, "record": record}


def test_wait_while_a_query_finishes_a_lease_probe_sees_the_release_done(box, monkeypatch):
    workspace, claim = _lease_probe_finishing(box, monkeypatch)
    state = _before_final_write(
        box,
        monkeypatch,
        lambda: _in_window(box, lambda: box.gateway._assist_wait(TASK, timeout_seconds=0.0)),
    )
    result = box.gateway._assist_refresh(TASK)
    assert state.get("other") is not None, "the wait never ran before the final write"
    answer, seen = state["other"]["answer"], state["other"]["record"]
    assert (answer["status"], answer["blocker"], answer["reconciliation_required"]) == (
        "COMPLETED",
        None,
        False,
    ), answer
    assert answer["next_action"] == "none", answer
    _assert_probe_completed(seen)
    record = box.gateway._assist_read(TASK)
    assert record is not None
    _assert_probe_completed(record)
    assert result is not None
    _assert_probe_completed(result)
    assert claim.releases == 1, claim.releases
    assert TASK not in box.gateway._assist_processes
    assert not workspace.exists()


def test_cancel_while_a_query_finishes_a_lease_probe_records_no_lease_failure(box, monkeypatch):
    workspace, claim = _lease_probe_finishing(box, monkeypatch)
    state = _before_final_write(
        box, monkeypatch, lambda: _in_window(box, lambda: box.gateway._assist_cancel(TASK))
    )
    result = box.gateway._assist_refresh(TASK)
    assert state.get("other") is not None, "the cancel never ran before the final write"
    answer, seen = state["other"]["answer"], state["other"]["record"]
    assert (answer["status"], answer["blocker"], answer["reconciliation_required"]) == (
        "COMPLETED",
        None,
        False,
    ), answer
    # Nothing the final write has to overwrite: no CANCELLED, no PROCESS_LOST, no hold.
    _assert_probe_completed(seen)
    record = box.gateway._assist_read(TASK)
    assert record is not None
    _assert_probe_completed(record)
    assert result is not None
    _assert_probe_completed(result)
    assert claim.releases == 1, claim.releases
    assert box.terminated == []
    assert TASK not in box.gateway._assist_processes
    assert not workspace.exists()


def test_reconcile_while_a_query_finishes_a_lease_probe_keeps_the_provider_outcome(
    box, monkeypatch
):
    """Without the fix the window's hold reaches reconcile, which settles the job as a
    retryable PROCESS_LOST failure and refuses the query's completed write (#3160 comment)."""
    from nexus.orchestrator import unified_mcp_gateway

    receipts: list = []

    class _Coordinator:
        def __init__(self, manager) -> None:
            pass

        def reconcile_claim_receipt(self, **kwargs):
            receipts.append(kwargs)
            return {"result": "ALREADY_ABSENT"}

    monkeypatch.setattr(unified_mcp_gateway, "CrossProcessLeaseCoordinator", _Coordinator)
    monkeypatch.setattr(unified_mcp_gateway, "get_account_pool_manager", lambda: object())
    workspace, claim = _lease_probe_finishing(box, monkeypatch)
    state = _before_final_write(
        box,
        monkeypatch,
        lambda: _in_window(box, lambda: box.gateway._task_reconcile({"task_id": TASK})),
    )
    box.gateway._assist_refresh(TASK)
    assert state.get("other") is not None, "the reconcile never ran before the final write"
    _assert_probe_completed(state["other"]["record"])
    record = box.gateway._assist_read(TASK)
    assert record is not None
    _assert_probe_completed(record)
    assert receipts == []
    assert claim.releases == 1, claim.releases
    assert not workspace.exists()


def test_lease_probe_whose_final_write_fails_releases_the_lease_once(box, monkeypatch):
    """The query released the claim, then its final write failed (the provider was already
    unregistered, #3144): the next query holds the job for reconciliation, which finds the
    lease receipt gone and settles it with the release recorded. The claim is released exactly
    once, and a later cancel releases nothing."""
    from nexus.orchestrator import unified_mcp_gateway

    receipts: list = []

    class _Coordinator:
        def __init__(self, manager) -> None:
            pass

        def reconcile_claim_receipt(self, **kwargs):
            receipts.append(kwargs)
            return {"result": "ALREADY_ABSENT"}

    monkeypatch.setattr(unified_mcp_gateway, "CrossProcessLeaseCoordinator", _Coordinator)
    monkeypatch.setattr(unified_mcp_gateway, "get_account_pool_manager", lambda: object())
    workspace, claim = _lease_probe_finishing(box, monkeypatch)
    write = box.gateway._assist_write
    failed: list = []

    def failing_write(job):
        if job.get("status") == "COMPLETED" and not failed:
            failed.append(dict(job))
            raise OSError("disk full")
        return write(job)

    monkeypatch.setattr(box.gateway, "_assist_write", failing_write)
    with pytest.raises(OSError, match="disk full"):
        box.gateway._assist_refresh(TASK)
    assert failed, "the final write was never attempted"
    assert claim.releases == 1, claim.releases
    held = box.gateway._assist_refresh(TASK)
    assert held is not None
    _assert_held(held, "ASSIST_PROVIDER_PROCESS_LOST")
    settled = box.gateway._task_reconcile({"task_id": TASK})
    assert (settled["status"], settled["blocker"]) == ("FAILED", "ASSIST_PROVIDER_PROCESS_LOST")
    record = box.gateway._assist_read(TASK)
    assert record is not None
    assert (record["account_lease_released"], record["account_lease_cleanup_status"]) == (
        True,
        "RELEASED",
    ), record
    assert [r["lease_id_hash"] for r in receipts] == [LEASE]
    assert claim.releases == 1, claim.releases
    box.gateway._assist_cancel(TASK)
    assert claim.releases == 1, claim.releases
    assert not workspace.exists()


class _FailingClaim(_Claim):
    def release(self) -> None:
        self.releases += 1
        raise RuntimeError("release failed")


def test_release_noted_only_for_the_lease_that_was_released(box):
    gateway = box.gateway
    claim = _Claim()
    gateway._assist_account_claims[TASK] = claim
    first: dict = {"account_lease_id_hash": LEASE}
    assert gateway._release_assist_account_claim(TASK, first) is True
    # A second call for the same lease: the release is done, by this job.
    again: dict = {"account_lease_id_hash": LEASE}
    assert gateway._release_assist_account_claim(TASK, again) is True
    assert (again["account_lease_released"], again["account_lease_cleanup_status"]) == (
        True,
        "RELEASED",
    )
    assert claim.releases == 1
    # Another lease of the task (a retry's) whose claim is gone: a lost claim.
    other: dict = {"account_lease_id_hash": "lease-3160-retry"}
    assert gateway._release_assist_account_claim(TASK, other) is False
    assert (other["account_lease_released"], other["account_lease_cleanup_status"]) == (
        False,
        "RECONCILIATION_REQUIRED",
    )
    # The same lease hash on another task: not that task's release.
    elsewhere: dict = {"account_lease_id_hash": LEASE}
    assert gateway._release_assist_account_claim("t3160-other", elsewhere) is False


def test_failed_release_is_not_noted_as_released(box):
    gateway = box.gateway
    claim = _FailingClaim()
    gateway._assist_account_claims[TASK] = claim
    first: dict = {"account_lease_id_hash": LEASE}
    assert gateway._release_assist_account_claim(TASK, first) is False
    assert first["account_lease_cleanup_status"] == "RELEASE_FAILED"
    again: dict = {"account_lease_id_hash": LEASE}
    assert gateway._release_assist_account_claim(TASK, again) is False
    assert (again["account_lease_released"], again["account_lease_cleanup_status"]) == (
        False,
        "RECONCILIATION_REQUIRED",
    )
    assert claim.releases == 1


def test_second_release_waits_for_a_release_in_progress(box):
    """A second call of the same job while the first is still releasing the claim waits for
    it and then finds the release done; it never sees the claim gone and unreleased."""
    gateway = box.gateway
    entered = threading.Event()
    proceed = threading.Event()

    class _SlowClaim(_Claim):
        def release(self) -> None:
            entered.set()
            assert proceed.wait(5), "the test never let the release finish"
            super().release()

    claim = _SlowClaim()
    gateway._assist_account_claims[TASK] = claim
    first: dict = {"account_lease_id_hash": LEASE}
    second: dict = {"account_lease_id_hash": LEASE}
    outcome: dict = {}
    releasing = threading.Thread(
        target=lambda: outcome.setdefault(
            "first", gateway._release_assist_account_claim(TASK, first)
        )
    )
    releasing.start()
    assert entered.wait(5), "the first release never started"
    # The second call's lock entry first tries the lock without waiting (#3180): the attempt
    # failing while the first release is held at ``proceed`` proves the second call blocked.
    lock = gateway._assist_lock
    attempted = threading.Event()
    blocked: list[bool] = []

    class _ProbingLock:
        def __enter__(self):
            if threading.current_thread() is racing and not attempted.is_set():
                got = lock.acquire(blocking=False)
                blocked.append(not got)
                attempted.set()
                if got:
                    return True
            return lock.__enter__()

        def __exit__(self, *exc):
            return lock.__exit__(*exc)

    gateway._assist_lock = _ProbingLock()
    racing = threading.Thread(
        target=lambda: outcome.setdefault(
            "second", gateway._release_assist_account_claim(TASK, second)
        )
    )
    racing.start()
    assert attempted.wait(5), "the second call never reached the lock"
    raced_early = "second" in outcome
    proceed.set()
    releasing.join(5)
    racing.join(5)
    gateway._assist_lock = lock
    assert blocked == [True], f"the second call found the lock free during the release: {second}"
    assert not raced_early, f"the second call did not wait for the release: {second}"
    assert outcome == {"first": True, "second": True}, (outcome, second)
    assert second["account_lease_cleanup_status"] == "RELEASED", second
    assert claim.releases == 1


# ---------------------------------------------------------------------------
# #3180: a real lease release that fails is recorded as failed; the released-lease note is
# keyed by the claim's own lease and dropped once the job settles; abandon, then release.
# ---------------------------------------------------------------------------


class _LeaseManager:
    """The pool manager behind a real ``AccountLeaseClaim``; no pool, nothing leased."""

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.released: list = []

    def release(self, lease) -> None:
        self.released.append(lease)
        if self.fail:
            raise RuntimeError("pool lease release failed")


class _BrokenLockFile:
    """A lock file object whose descriptor is gone."""

    closed = False

    def fileno(self) -> int:
        raise OSError("bad file descriptor")

    def close(self) -> None:
        self.closed = True


def _real_claim(tmp: Path, *, lease_id_hash: str = LEASE, manager=None, lock_file=None):
    """A real ``AccountLeaseClaim`` on a lock file and a receipt under ``tmp``: its flock is
    held by this test, and its manager is a stand-in."""
    import fcntl

    from nexus.services.agy_account_pool import AccountLeaseClaim

    tmp.mkdir(parents=True, exist_ok=True)
    lock_path = tmp / "alias-3180.lock"
    receipt_path = tmp / "alias-3180.receipt.json"
    receipt_path.write_text("{}\n", encoding="utf-8")
    if lock_file is None:
        lock_file = lock_path.open("a+")
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    return AccountLeaseClaim(
        lease=SimpleNamespace(lease_id="lease-3180"),
        lock_file_obj=lock_file,
        lock_path=lock_path,
        receipt_path=receipt_path,
        account_alias_hash="alias-3180",
        lease_id_hash=lease_id_hash,
        manager=manager if manager is not None else _LeaseManager(),
        internal_id="internal-3180",
    )


def _flock_is_free(path: Path) -> bool:
    import fcntl

    with path.open("a+") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return False
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        return True


def test_lease_claim_release_that_succeeds_records_no_error(tmp_path):
    manager = _LeaseManager()
    claim = _real_claim(tmp_path / "lease", manager=manager)
    assert claim.release() is None
    assert claim.release_errors == ()
    assert not claim.receipt_path.exists()
    assert _flock_is_free(claim.lock_path)
    assert len(manager.released) == 1


def test_lease_claim_release_keeps_every_failed_step_and_never_raises(tmp_path):
    """Each step still runs after an earlier one failed; release() itself does not raise, so
    the callers that ignore the outcome keep their behaviour."""
    manager = _LeaseManager(fail=True)
    claim = _real_claim(tmp_path / "lease", manager=manager, lock_file=_BrokenLockFile())
    claim.receipt_path.unlink()
    claim.receipt_path.mkdir()  # exists, and unlink() refuses a directory
    assert claim.release() is None
    assert [error.split(":")[0] for error in claim.release_errors] == [
        "receipt_unlink",
        "lock_release",
        "manager_release",
    ], claim.release_errors
    assert claim.release_errors[2] == "manager_release:RuntimeError"
    assert claim.released is True
    # A repeated release does nothing and keeps the failure.
    claim.release()
    assert len(claim.release_errors) == 3
    assert len(manager.released) == 1


def test_failed_real_lease_release_is_recorded_as_failed(box):
    gateway = box.gateway
    manager = _LeaseManager(fail=True)
    claim = _real_claim(box.tmp / "lease", manager=manager)
    gateway._assist_account_claims[TASK] = claim
    first: dict = {"account_lease_id_hash": LEASE}
    assert gateway._release_assist_account_claim(TASK, first) is False
    assert (
        first["account_lease_released"],
        first["account_lease_cleanup_status"],
        first["reconciliation_required"],
    ) == (False, "RELEASE_FAILED", True), first
    assert TASK not in gateway._assist_account_claims
    assert TASK not in (getattr(gateway, "_assist_released_leases", None) or {})
    again: dict = {"account_lease_id_hash": LEASE}
    assert gateway._release_assist_account_claim(TASK, again) is False
    assert again["account_lease_cleanup_status"] == "RECONCILIATION_REQUIRED", again
    assert len(manager.released) == 1


def test_lease_probe_whose_real_release_fails_is_held_then_reconciled(box, monkeypatch):
    """The finishing query's release fails in a real claim: the job is held for
    reconciliation (no RELEASED anywhere), and the reconcile checks the receipt of that lease
    before it settles the job."""
    from nexus.orchestrator import unified_mcp_gateway

    receipts: list = []

    class _Coordinator:
        def __init__(self, manager) -> None:
            pass

        def reconcile_claim_receipt(self, **kwargs):
            receipts.append(kwargs)
            return {"result": "LEASE_RECEIPT_REMOVED"}

    monkeypatch.setattr(unified_mcp_gateway, "CrossProcessLeaseCoordinator", _Coordinator)
    monkeypatch.setattr(unified_mcp_gateway, "get_account_pool_manager", lambda: object())
    workspace, _ = _lease_probe_finishing(box, monkeypatch)
    manager = _LeaseManager(fail=True)
    box.gateway._assist_account_claims[TASK] = _real_claim(box.tmp / "lease", manager=manager)
    held = box.gateway._assist_refresh(TASK)
    assert held is not None
    _assert_held(held, "ASSIST_ACCOUNT_LEASE_RECONCILIATION_REQUIRED")
    record = box.gateway._assist_read(TASK)
    assert record is not None
    _assert_held(record, "ASSIST_ACCOUNT_LEASE_RECONCILIATION_REQUIRED")
    assert (record["account_lease_released"], record["account_lease_cleanup_status"]) == (
        False,
        "RELEASE_FAILED",
    ), record
    assert receipts == []
    settled = box.gateway._task_reconcile({"task_id": TASK})
    assert settled["status"] == "FAILED", settled
    assert [r["lease_id_hash"] for r in receipts] == [LEASE]
    assert len(manager.released) == 1
    assert not workspace.exists()


def test_release_notes_the_claims_own_lease(box):
    """A caller whose record names another lease (a stale record) releases the claim, but the
    note names the lease that was released."""
    gateway = box.gateway
    gateway._assist_account_claims[TASK] = _Claim(lease_id_hash=LEASE)
    stale: dict = {"account_lease_id_hash": "lease-3180-stale"}
    assert gateway._release_assist_account_claim(TASK, stale) is True
    again_stale: dict = {"account_lease_id_hash": "lease-3180-stale"}
    assert gateway._release_assist_account_claim(TASK, again_stale) is False
    assert again_stale["account_lease_cleanup_status"] == "RECONCILIATION_REQUIRED"
    own: dict = {"account_lease_id_hash": LEASE}
    assert gateway._release_assist_account_claim(TASK, own) is True
    assert own["account_lease_cleanup_status"] == "RELEASED"


def test_released_lease_note_is_kept_until_the_job_settles(box):
    gateway = box.gateway
    _running_job(box)
    gateway._assist_account_claims[TASK] = _Claim()
    assert gateway._release_assist_account_claim(TASK, {"account_lease_id_hash": LEASE})
    record = gateway._assist_read(TASK)
    assert record is not None
    # A running or held record of the job keeps the note: a call of the job may still need it.
    gateway._assist_write({**record, "status": "RUNNING"})
    gateway._assist_write({
        **record,
        "status": "UNKNOWN_REQUIRES_RECONCILE",
        "reconciliation_required": True,
    })
    gateway._assist_write({**record, "status": "CANCELLED", "reconciliation_required": True})
    assert gateway._assist_released_leases == {TASK: LEASE}
    gateway._assist_write({**record, "status": "COMPLETED", "reconciliation_required": False})
    assert gateway._assist_released_leases == {}


def test_finished_lease_probe_leaves_no_released_lease_note(box, monkeypatch):
    workspace, claim = _lease_probe_finishing(box, monkeypatch)
    result = box.gateway._assist_refresh(TASK)
    assert result is not None
    _assert_probe_completed(result)
    assert claim.releases == 1
    assert TASK not in box.gateway._assist_released_leases
    assert not workspace.exists()


def test_wait_in_the_window_settles_the_job_and_drops_the_note(box, monkeypatch):
    """The wait in the window settles the job with the release recorded, which drops the note;
    the query's final write still lands, and a later cancel releases nothing."""
    workspace, claim = _lease_probe_finishing(box, monkeypatch)

    def wait_then_look() -> dict:
        noted = dict(box.gateway._assist_released_leases)
        answer = box.gateway._assist_wait(TASK, timeout_seconds=0.0)
        return {
            "noted": noted,
            "answer": answer,
            "after": dict(box.gateway._assist_released_leases),
        }

    state = _before_final_write(box, monkeypatch, wait_then_look)
    result = box.gateway._assist_refresh(TASK)
    assert state.get("other") is not None, "the wait never ran before the final write"
    assert state["other"]["noted"] == {TASK: LEASE}
    assert state["other"]["answer"]["status"] == "COMPLETED", state["other"]["answer"]
    assert state["other"]["after"] == {}
    assert result is not None
    _assert_probe_completed(result)
    box.gateway._assist_cancel(TASK)
    record = box.gateway._assist_read(TASK)
    assert record is not None
    _assert_probe_completed(record)
    assert claim.releases == 1
    assert not workspace.exists()


class _AbandonedClaim(_Claim):
    def __init__(self, lease_id_hash: str = LEASE) -> None:
        super().__init__(lease_id_hash)
        self.abandoned = 0

    def abandon_parent_reference(self) -> None:
        self.abandoned += 1


def test_abandoned_claim_then_release_of_the_same_task_is_a_lost_claim(box):
    """A claim abandoned (its provider may still run on the account) and then released for
    the same task: the release finds no claim and no note, so the lease still needs
    reconciliation; nothing is released."""
    gateway = box.gateway
    claim = _AbandonedClaim()
    gateway._assist_account_claims[TASK] = claim
    abandoned: dict = {"account_lease_id_hash": LEASE}
    assert gateway._abandon_assist_account_claim(TASK, abandoned) is None
    assert abandoned["account_lease_cleanup_status"] == "RECONCILIATION_REQUIRED"
    later: dict = {"account_lease_id_hash": LEASE}
    assert gateway._release_assist_account_claim(TASK, later) is False
    assert (
        later["account_lease_released"],
        later["account_lease_cleanup_status"],
    ) == (False, "RECONCILIATION_REQUIRED"), later
    assert (claim.abandoned, claim.releases) == (1, 0)
    assert TASK not in (getattr(gateway, "_assist_released_leases", None) or {})
