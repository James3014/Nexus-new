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
import sys
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
    """An Agy account claim stand-in that counts its releases; no real lease behind it."""

    def __init__(self) -> None:
        self.releases = 0

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
