"""#3076 (review follow-ups of #3072): the gateway keeps an Agy account lease and an assist
workspace until the provider's process group is known to be gone.

Real processes appear in one test only (the model-probe identity-drift launch): a provider stub
started by the gateway itself, whose grandchild ignores SIGTERM and stays in the stub's process
group, as in tests/engine/test_open_swe_and_probe_reaping_3052.py. Its cleanup signals only a
pid read from this test's own pid file whose ``ps`` command line names this test's tmp path.
Every other test uses a fake provider whose pid is above any pid_max (Linux 2**22, macOS 99999),
with ``os.kill``/``os.killpg`` and the group listing replaced: nothing is signalled on the host.
No real lease (a tmp lock file and a fake manager), no live gateway, no Agy.
"""

from __future__ import annotations

import fcntl
import os
import signal
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from nexus.core import argv_command
from nexus.orchestrator.unified_mcp_gateway import UnifiedMCPGateway
from nexus.orchestrator.unified_mcp_gateway_parts import assist_jobs, assist_response, model_probe
from nexus.services import open_swe_external_intelligence as osei
from nexus.services.agy_account_pool import AccountLeaseClaim
from tests.engine.test_open_swe_and_probe_reaping_3052 import (
    DOUBLE_FORK,
    _FakeManager,
    _lock_free,
    _ours_alive,
    _wait_pidfile,
    _write,
    box,  # noqa: F401 - pytest fixture
)
from tests.nexus.orchestrator.test_unified_mcp_gateway import FakeService

# Above Linux's largest pid_max (2**22) and macOS's (99999): never a real process.
FAKE_PID = 2**22 + 4321


class _FakeProvider:
    """A registered provider Popen stand-in; nothing real behind its pid."""

    def __init__(self, pid: int = FAKE_PID, returncode: int | None = None) -> None:
        self.pid = pid
        self.returncode = returncode

    def wait(self, timeout=None):
        if self.returncode is None:
            self.returncode = -signal.SIGKILL
        return self.returncode

    def poll(self):
        return self.returncode


class _FakeGroup:
    """os.kill / os.killpg / the group listing for one fake provider group: a leader that dies
    on SIGTERM and one member that ignores SIGTERM (and, if ``member_survives_kill``, SIGKILL)."""

    def __init__(self, *, member_survives_kill: bool = False) -> None:
        self.leader_alive = True
        self.member_alive = True
        self.member_survives_kill = member_survives_kill
        self.sent: list[int] = []

    def kill(self, pid: int, sig: int) -> None:
        assert pid == FAKE_PID, f"os.kill on a pid this test does not own: {pid}"
        if sig != 0:
            self.sent.append(sig)
        if not self.leader_alive:
            raise ProcessLookupError(pid)

    def killpg(self, pgid: int, sig: int) -> None:
        assert pgid == FAKE_PID, f"os.killpg on a group this test does not own: {pgid}"
        self.sent.append(sig)
        self.leader_alive = False
        if sig == signal.SIGKILL and not self.member_survives_kill:
            self.member_alive = False

    def live_members(self, pgid: int) -> list[int]:
        assert pgid == FAKE_PID, f"listing a group this test does not own: {pgid}"
        return ([FAKE_PID] if self.leader_alive else []) + (
            [FAKE_PID + 1] if self.member_alive else []
        )


def _gateway(tmp_path: Path) -> UnifiedMCPGateway:
    service = FakeService()
    service.state_dir = tmp_path
    return UnifiedMCPGateway(service=service)


def _assist_job(tmp_path: Path, **fields) -> tuple[dict, Path]:
    workspace = tmp_path / "assist-workspace"
    workspace.mkdir()
    (workspace / "partial.txt").write_text("partial", encoding="utf-8")
    job = {
        "schema": "nexus.assisted_provider_job.v1",
        "task_id": "t3076",
        "job_id": "assist-3076",
        "job_kind": "assist",
        "status": "RUNNING",
        "provider": "cline",
        "pid": FAKE_PID,
        "pgid": FAKE_PID,
        "workspace_mode": "isolated",
        "workspace_root": str(workspace),
        "filesystem_before": {},
        "stdout_artifact": str(tmp_path / "out.txt"),
        "stderr_artifact": str(tmp_path / "err.txt"),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "attempt_history": [],
    }
    job.update(fields)
    return job, workspace


# ---------------------------------------------------------------------------
# Item 9 (pre-existing): model probe, executable identity changed during launch
# ---------------------------------------------------------------------------


def _drift_provider_stub(tmp: Path, pidfile: Path) -> Path:
    """Leader dies on SIGTERM; its grandchild stays in the group and ignores SIGTERM."""
    return _write(
        tmp / "agy_drift_provider_stub.py",
        f"#!{sys.executable}\n"
        + DOUBLE_FORK
        + "import signal\nsignal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        + f"spawn_grandchild({str(pidfile)!r}, False)\n"
        + "signal.signal(signal.SIGTERM, signal.SIG_DFL)\n"
        + "time.sleep(60)\n",
        executable=True,
    )


def test_model_probe_identity_drift_kills_group_before_lease_release(box, monkeypatch):  # noqa: F811
    """The executable changed while the probe launched: the provider is stopped and the Agy
    lease released only once its whole process group is gone, not after a SIGTERM that only
    the leader obeyed."""
    tmp, pidfile, marker = box
    stub = _drift_provider_stub(tmp, pidfile)
    lock_path, receipt_path = tmp / "account.lock", tmp / "account.receipt.json"
    receipt_path.write_text("{}")
    lock_obj = open(lock_path, "a+")  # noqa: SIM115 - owned by the claim
    fcntl.flock(lock_obj.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    manager = _FakeManager()
    claim = AccountLeaseClaim(
        lease=SimpleNamespace(execution_env={"PATH": "/usr/bin:/bin"}),  # pyright: ignore[reportArgumentType]
        lock_file_obj=lock_obj,
        lock_path=lock_path,
        receipt_path=receipt_path,
        account_alias_hash="alias",
        lease_id_hash="lease",
        manager=manager,
        internal_id="stub",
    )
    gateway = _gateway(tmp)
    calls = {"n": 0}

    def resolve(provider):
        calls["n"] += 1
        if calls["n"] <= 2:
            return {"default_model": "gemini-3.6-flash-medium"}, str(stub)
        # Post-launch re-check: the grandchild is running by now, and the executable "changed".
        _wait_pidfile(pidfile)
        return {"default_model": "gemini-3.6-flash-medium"}, "/bin/echo"

    real_run = subprocess.run

    def run(command, *args, **kwargs):
        if list(command)[-1:] == ["--version"]:
            return SimpleNamespace(returncode=0, stdout="agy 1.2.3\n", stderr="")
        return real_run(command, *args, **kwargs)

    monkeypatch.setattr(gateway, "_provider_executable", resolve)
    monkeypatch.setattr(gateway, "_acquire_agy_probe_claim", lambda **kwargs: claim)
    monkeypatch.setattr(model_probe, "agy_pool_stopped", lambda: False)
    monkeypatch.setattr("nexus.orchestrator.unified_mcp_gateway._git", lambda *a, **k: "a" * 40)
    monkeypatch.setattr("nexus.orchestrator.unified_mcp_gateway.subprocess.run", run)

    result = gateway._model_probe_submit({
        "task_id": "drift-3076",
        "provider": "agy",
        "model": "gemini-3.6-flash-medium",
        "prompt": "probe",
        "output_schema": {"type": "object"},
    })
    pid = _wait_pidfile(pidfile)
    lease_released = bool(manager.released) and _lock_free(lock_path)
    grandchild_alive = _ours_alive(pid, marker)
    if grandchild_alive:
        assert not lease_released, (
            f"grandchild {pid} still alive after the identity-drift branch released the Agy "
            f"account lease (result {result['status']}/{result['blocker']})"
        )
        assert result["status"] == "UNKNOWN_REQUIRES_RECONCILE", result
    assert not grandchild_alive, (
        f"grandchild {pid} still alive after the identity-drift branch "
        f"({result['status']}/{result['blocker']}, lease released={lease_released})"
    )
    assert result["status"] == "FAILED", result
    assert result["blocker"] == "ASSIST_PROVIDER_IDENTITY_DRIFT"
    assert result["account_lease_cleanup_status"] == "RELEASED"
    assert lease_released and not receipt_path.exists()


def test_model_probe_identity_drift_unclean_group_keeps_lease_and_workspace(monkeypatch, tmp_path):
    """The group cannot be confirmed empty: the lease is abandoned (not released), the
    workspace is kept and the probe needs reconciliation."""
    gateway = _gateway(tmp_path)
    resolutions = iter([
        ({"default_model": "glm-5.2"}, "/bin/echo"),
        ({"default_model": "glm-5.2"}, "/bin/echo"),
        ({"default_model": "glm-5.2"}, "/bin/false"),
    ])
    claim = SimpleNamespace(
        account_alias_hash="a" * 12,
        lease_id_hash="b" * 12,
        lease=SimpleNamespace(execution_env={}),
        lock_file_obj=SimpleNamespace(fileno=lambda: 80),
        released=[],
        abandoned=[],
    )
    claim.release = lambda: claim.released.append(True)
    claim.abandon_parent_reference = lambda: claim.abandoned.append(True)
    terminated = []

    def terminate(process):
        terminated.append(process)
        return False

    monkeypatch.setattr(gateway, "_provider_executable", lambda provider: next(resolutions))
    monkeypatch.setattr(gateway, "_acquire_agy_probe_claim", lambda **kwargs: claim)
    monkeypatch.setattr(model_probe, "agy_pool_stopped", lambda: False)
    monkeypatch.setattr(model_probe, "_terminate_provider_group", terminate, raising=False)
    monkeypatch.setattr("nexus.orchestrator.unified_mcp_gateway._git", lambda *a, **k: "a" * 40)
    monkeypatch.setattr(
        "nexus.orchestrator.unified_mcp_gateway.subprocess.run",
        lambda command, **kwargs: SimpleNamespace(returncode=0, stdout="agy 1.2.3\n", stderr=""),
    )
    monkeypatch.setattr(
        "nexus.orchestrator.unified_mcp_gateway.subprocess.Popen",
        lambda *args, **kwargs: _FakeProvider(),
    )
    result = gateway._model_probe_submit({
        "task_id": "drift-unclean-3076",
        "provider": "agy",
        "model": "gemini-3.6-flash-medium",
        "prompt": "probe",
        "output_schema": {"type": "object"},
    })
    assert len(terminated) == 1
    assert result["status"] == "UNKNOWN_REQUIRES_RECONCILE", result
    assert result["blocker"] == "ASSIST_PROVIDER_IDENTITY_DRIFT_CLEANUP_INCOMPLETE"
    assert result["reconciliation_required"] is True
    assert result["account_lease_cleanup_status"] == "RECONCILIATION_REQUIRED"
    assert claim.released == [] and claim.abandoned == [True]
    workspace = Path(result["workspace_root"])
    try:
        assert workspace.exists(), "workspace removed while a provider descendant may still use it"
    finally:
        if workspace.name.startswith("nexus-probe-drift-unclean-3076"):
            import shutil

            shutil.rmtree(workspace, ignore_errors=True)


# ---------------------------------------------------------------------------
# Item 10 (pre-existing): cancel and reconcile remove the workspace only once the group is gone
# ---------------------------------------------------------------------------


def test_cancel_keeps_workspace_when_registered_provider_not_terminated(monkeypatch, tmp_path):
    gateway = _gateway(tmp_path)
    job, workspace = _assist_job(tmp_path)
    gateway._assist_write(job)
    gateway._assist_processes["t3076"] = _FakeProvider()  # pyright: ignore[reportArgumentType]
    monkeypatch.setattr(assist_response, "kill_group_if_exited", lambda process: False)
    monkeypatch.setattr(assist_jobs, "_terminate_provider_group", lambda process: False)
    cancelled = gateway._assist_cancel("t3076")
    assert workspace.exists(), (
        "cancel removed the workspace although the provider's group was not confirmed gone"
    )
    assert cancelled["status"] == "UNKNOWN_REQUIRES_RECONCILE", cancelled
    assert cancelled["blocker"] == "ASSIST_CANCEL_CLEANUP_INCOMPLETE"
    assert cancelled["reconciliation_required"] is True
    assert cancelled["process_killed"] is False
    assert cancelled["process_cleanup"] is False
    assert cancelled["next_action"] == "nexus_task_reconcile"


def test_cancel_removes_workspace_once_registered_provider_terminated(monkeypatch, tmp_path):
    gateway = _gateway(tmp_path)
    job, workspace = _assist_job(tmp_path)
    gateway._assist_write(job)
    gateway._assist_processes["t3076"] = _FakeProvider()  # pyright: ignore[reportArgumentType]
    monkeypatch.setattr(assist_response, "kill_group_if_exited", lambda process: False)
    monkeypatch.setattr(assist_jobs, "_terminate_provider_group", lambda process: True)
    cancelled = gateway._assist_cancel("t3076")
    assert cancelled["status"] == "CANCELLED", cancelled
    assert cancelled["blocker"] == "ASSIST_CANCELLED"
    assert cancelled["process_cleanup"] is True
    assert not workspace.exists()


@pytest.mark.parametrize(
    "blocker", ["ASSIST_PROVIDER_GROUP_CLEANUP_INCOMPLETE", "ASSIST_PROVIDER_PROCESS_LOST"]
)
def test_cancel_of_reconcile_pending_job_keeps_workspace_while_group_has_members(
    monkeypatch, tmp_path, blocker
):
    gateway = _gateway(tmp_path)
    job, workspace = _assist_job(
        tmp_path,
        status="UNKNOWN_REQUIRES_RECONCILE",
        blocker=blocker,
        reconciliation_required=True,
        durable_exit_marker=blocker == "ASSIST_PROVIDER_GROUP_CLEANUP_INCOMPLETE",
    )
    gateway._assist_write(job)
    group = _FakeGroup()
    group.leader_alive = False
    monkeypatch.setattr(argv_command, "_live_group_members", group.live_members)
    cancelled = gateway._assist_cancel("t3076")
    assert workspace.exists(), (
        "cancel removed the workspace of a reconcile-pending job while its provider group "
        "still had a live member"
    )
    assert cancelled["status"] == "UNKNOWN_REQUIRES_RECONCILE", cancelled
    assert cancelled["blocker"] == blocker
    assert cancelled["reconciliation_required"] is True
    assert cancelled["process_cleanup"] is False
    assert group.sent == [], "a group the gateway does not hold must not be signalled here"


def test_cancel_of_reconcile_pending_job_removes_workspace_once_group_empty(monkeypatch, tmp_path):
    gateway = _gateway(tmp_path)
    job, workspace = _assist_job(
        tmp_path,
        status="UNKNOWN_REQUIRES_RECONCILE",
        blocker="ASSIST_PROVIDER_GROUP_CLEANUP_INCOMPLETE",
        reconciliation_required=True,
    )
    gateway._assist_write(job)
    group = _FakeGroup()
    group.leader_alive = group.member_alive = False
    monkeypatch.setattr(argv_command, "_live_group_members", group.live_members)
    cancelled = gateway._assist_cancel("t3076")
    assert cancelled["status"] == "CANCELLED", cancelled
    assert cancelled["process_cleanup"] is True
    assert not workspace.exists()


def test_cancel_of_reconcile_pending_job_keeps_workspace_when_group_cannot_be_listed(
    monkeypatch, tmp_path
):
    gateway = _gateway(tmp_path)
    job, workspace = _assist_job(
        tmp_path,
        status="UNKNOWN_REQUIRES_RECONCILE",
        blocker="ASSIST_PROVIDER_GROUP_CLEANUP_INCOMPLETE",
        reconciliation_required=True,
    )
    gateway._assist_write(job)
    monkeypatch.setattr(argv_command, "_live_group_members", lambda pgid: None)
    cancelled = gateway._assist_cancel("t3076")
    assert workspace.exists()
    assert cancelled["status"] == "UNKNOWN_REQUIRES_RECONCILE", cancelled


def test_reconcile_keeps_workspace_while_provider_group_has_members(monkeypatch, tmp_path):
    gateway = _gateway(tmp_path)
    job, workspace = _assist_job(
        tmp_path,
        status="UNKNOWN_REQUIRES_RECONCILE",
        blocker="ASSIST_PROVIDER_PROCESS_LOST",
        reconciliation_required=True,
    )
    gateway._assist_write(job)
    group = _FakeGroup()
    group.leader_alive = False
    monkeypatch.setattr(os, "kill", group.kill)
    monkeypatch.setattr(argv_command, "_live_group_members", group.live_members)
    reconciled = gateway._task_reconcile({"task_id": "t3076"})
    assert workspace.exists(), (
        "reconcile removed the workspace while the provider group still had a live member"
    )
    assert reconciled["status"] == "UNKNOWN_REQUIRES_RECONCILE", reconciled
    assert reconciled["reconciliation_required"] is True
    assert reconciled["process_cleanup"] is False
    assert reconciled["next_action"] == "nexus_task_reconcile"
    assert group.sent == []

    group.member_alive = False
    converged = gateway._task_reconcile({"task_id": "t3076"})
    assert converged["status"] == "FAILED", converged
    assert converged["reconciliation_required"] is False
    assert converged["process_cleanup"] is True
    assert not workspace.exists()


def test_reconcile_leaves_lease_alone_while_provider_group_has_members(monkeypatch, tmp_path):
    """The lease receipt is not reconciled while a provider group member may still hold it."""
    reconciled_leases = []

    class Coordinator:
        def __init__(self, manager):
            pass

        def reconcile_claim_receipt(self, **kwargs):
            reconciled_leases.append(kwargs)
            return {"result": "LEASE_RECEIPT_REMOVED"}

    monkeypatch.setattr(
        "nexus.orchestrator.unified_mcp_gateway.get_account_pool_manager", lambda: None
    )
    monkeypatch.setattr(
        "nexus.orchestrator.unified_mcp_gateway.CrossProcessLeaseCoordinator", Coordinator
    )
    gateway = _gateway(tmp_path)
    job, workspace = _assist_job(
        tmp_path,
        job_kind="model_probe",
        provider="agy",
        status="UNKNOWN_REQUIRES_RECONCILE",
        blocker="ASSIST_PROVIDER_GROUP_CLEANUP_INCOMPLETE",
        reconciliation_required=True,
        account_alias_hash="a" * 12,
        account_lease_id_hash="b" * 12,
        account_lease_owner_pid=12345,
        account_lease_released=False,
        account_lease_cleanup_status="RECONCILIATION_REQUIRED",
    )
    gateway._assist_write(job)
    group = _FakeGroup()
    group.leader_alive = False
    monkeypatch.setattr(argv_command, "_live_group_members", group.live_members)
    reconciled = gateway._task_reconcile({"task_id": "t3076"})
    assert reconciled["status"] == "UNKNOWN_REQUIRES_RECONCILE", reconciled
    assert reconciled["account_lease_cleanup_status"] == "RECONCILIATION_REQUIRED"
    assert reconciled_leases == []
    assert workspace.exists()


@pytest.mark.parametrize("member_survives_kill", [False, True])
def test_restarted_gateway_cancel_needs_an_empty_group(monkeypatch, tmp_path, member_survives_kill):
    """After a gateway restart the provider is not this process's child: its exit cannot be
    awaited without reaping it. A leader that died on SIGTERM while a group member ignored it
    is not a terminated provider: the group gets SIGKILL, and the workspace is removed only
    once a listing finds the group empty."""
    gateway = _gateway(tmp_path)
    job, workspace = _assist_job(tmp_path)
    gateway._assist_write(job)
    group = _FakeGroup(member_survives_kill=member_survives_kill)
    monkeypatch.setattr(os, "kill", group.kill)
    monkeypatch.setattr(os, "killpg", group.killpg)
    monkeypatch.setattr(argv_command, "_live_group_members", group.live_members)
    monkeypatch.setattr(assist_jobs, "_UNOWNED_GROUP_SETTLE_SECONDS", 0.3, raising=False)
    cancelled = gateway._assist_cancel("t3076")
    assert group.sent[:1] == [signal.SIGTERM]
    if member_survives_kill:
        assert workspace.exists(), (
            "cancel removed the workspace while a provider group member survived "
            f"(signals sent: {group.sent})"
        )
        assert cancelled["status"] == "UNKNOWN_REQUIRES_RECONCILE", cancelled
        assert cancelled["blocker"] == "ASSIST_CANCEL_CLEANUP_INCOMPLETE"
        assert cancelled["reconciliation_required"] is True
        assert cancelled["process_cleanup"] is False
    else:
        assert group.sent == [signal.SIGTERM, signal.SIGKILL], (
            "the leader died on SIGTERM but a group member ignored it; cancel stopped there "
            f"(signals sent: {group.sent})"
        )
        assert cancelled["status"] == "CANCELLED", cancelled
        assert cancelled["process_killed"] is True
        assert not workspace.exists()


# ---------------------------------------------------------------------------
# Item 7: kill_group_if_exited on a provider that is already reaped
# ---------------------------------------------------------------------------


def test_kill_group_if_exited_on_reaped_child_asks_and_signals_nothing(monkeypatch):
    """returncode set: the pid is free and may name another child of this process by now."""
    asked: list[tuple[str, int]] = []
    monkeypatch.setattr(
        argv_command, "_leader_unreaped", lambda pid: asked.append(("unreaped", pid)) or True
    )
    monkeypatch.setattr(
        argv_command,
        "_wait_leader_unreaped",
        lambda pid, deadline: asked.append(("wait", pid)) or True,
    )
    monkeypatch.setattr(
        argv_command, "_kill_process_group", lambda pgid: asked.append(("killpg", pgid))
    )
    with pytest.raises(ChildProcessError):
        argv_command.kill_group_if_exited(_FakeProvider(returncode=0))  # pyright: ignore[reportArgumentType]
    assert asked == []


# ---------------------------------------------------------------------------
# Item 6: one provider's settle does not hold up another's
# ---------------------------------------------------------------------------


def _settle_in_thread(process, results):
    job = {"job_kind": "assist", "provider": "cline"}
    thread = threading.Thread(
        target=lambda: results.append(assist_response._settle_provider_group(job, process)),
        daemon=True,
    )
    thread.start()
    return thread


def test_settle_of_one_provider_does_not_wait_for_another(monkeypatch):
    slow, other = _FakeProvider(FAKE_PID), _FakeProvider(FAKE_PID + 2)
    entered, release = threading.Event(), threading.Event()

    def exited(process):
        if process is slow:
            entered.set()
            release.wait(10)
        return False

    monkeypatch.setattr(assist_response, "kill_group_if_exited", exited)
    slow_results: list = []
    other_results: list = []
    slow_thread = _settle_in_thread(slow, slow_results)
    try:
        assert entered.wait(5)
        other_thread = _settle_in_thread(other, other_results)
        other_thread.join(2)
        assert other_results == [(False, True, False)], (
            "settling one provider waited for another provider's settle (module-wide lock)"
        )
    finally:
        release.set()
        slow_thread.join(5)
    assert slow_results == [(False, True, False)]


def test_settles_of_the_same_provider_stay_serialized(monkeypatch):
    process = _FakeProvider(FAKE_PID)
    entered, release = threading.Event(), threading.Event()
    calls = {"n": 0}

    def exited(p):
        calls["n"] += 1
        if calls["n"] == 1:
            entered.set()
            release.wait(10)
        return False

    monkeypatch.setattr(assist_response, "kill_group_if_exited", exited)
    first: list = []
    second: list = []
    first_thread = _settle_in_thread(process, first)
    try:
        assert entered.wait(5)
        second_thread = _settle_in_thread(process, second)
        second_thread.join(0.5)
        assert second == [] and calls["n"] == 1, "two settles of one provider ran at once"
    finally:
        release.set()
        first_thread.join(5)
    second_thread.join(5)
    assert first == second == [(False, True, False)]


# ---------------------------------------------------------------------------
# Item 8: test gaps that let mutants survive
# ---------------------------------------------------------------------------


def test_cancel_escalates_to_sigkill_when_provider_ignores_sigterm(monkeypatch):
    process = _FakeProvider(FAKE_PID)
    sent: list[tuple[int, int]] = []

    def killpg(pgid, sig):
        assert pgid == FAKE_PID
        sent.append((pgid, sig))

    def exited(p):
        if (FAKE_PID, signal.SIGKILL) in sent:
            p.returncode = -signal.SIGKILL
            return True
        return False

    monkeypatch.setattr(os, "killpg", killpg)
    monkeypatch.setattr(assist_response, "kill_group_if_exited", exited)
    monkeypatch.setattr(assist_response, "_PROVIDER_KILL_SETTLE_SECONDS", 0.2)
    assert assist_response._terminate_provider_group(process) is True  # pyright: ignore[reportArgumentType]
    assert sent == [(FAKE_PID, signal.SIGTERM), (FAKE_PID, signal.SIGKILL)]


def test_cancel_of_provider_reaped_elsewhere_signals_nothing(monkeypatch):
    sent: list[tuple[int, int]] = []

    def exited(p):
        raise AssertionError("an already reaped provider must not be checked or signalled")

    monkeypatch.setattr(os, "killpg", lambda pgid, sig: sent.append((pgid, sig)))
    monkeypatch.setattr(assist_response, "kill_group_if_exited", exited)
    reaped = _FakeProvider(FAKE_PID, returncode=0)
    assert assist_response._terminate_provider_group(reaped) is False  # pyright: ignore[reportArgumentType]
    assert sent == []


@pytest.mark.parametrize("error", [PermissionError, ChildProcessError])
def test_open_swe_runtime_cleanup_incomplete_is_reported(monkeypatch, tmp_path, error):
    def unclean(process, timeout):
        raise error("group member survived")

    monkeypatch.setattr(osei, "require_child_stays_unreaped", lambda: None)
    monkeypatch.setattr(
        osei.subprocess, "Popen", lambda *args, **kwargs: SimpleNamespace(stdout=None, stderr=None)
    )
    monkeypatch.setattr(osei, "communicate_then_kill_group", unclean)
    assert osei._runtime_call(
        str(tmp_path / "runtime"), {"operation": "semantic_run"}, provider_id="none", timeout=1.0
    ) == (None, "", True, "runtime_cleanup_incomplete")


def test_cancel_of_job_that_never_started_a_provider_removes_workspace(tmp_path):
    """No registered process and no pid: there is no group to wait for (Ultra Review, #3083)."""
    gateway = _gateway(tmp_path)
    job, workspace = _assist_job(tmp_path, status="SUBMITTED")
    job.pop("pid")
    job.pop("pgid")
    gateway._assist_write(job)
    cancelled = gateway._assist_cancel("t3076")
    assert cancelled["status"] == "CANCELLED", cancelled
    assert cancelled["process_cleanup"] is True
    assert cancelled["reconciliation_required"] is False
    assert not workspace.exists()


def test_reconcile_converges_when_workspace_already_gone(monkeypatch, tmp_path):
    """A lease-reconcile-pending probe whose group was killed clean and whose workspace was
    already removed is not held by a group listing that now shows members (a reused id), nor
    is a job whose workspace an operator removed by hand; the lease receipt keeps its own
    flock check."""
    reconciled_leases = []

    class Coordinator:
        def __init__(self, manager):
            pass

        def reconcile_claim_receipt(self, **kwargs):
            reconciled_leases.append(kwargs)
            return {"result": "LEASE_RECEIPT_REMOVED"}

    monkeypatch.setattr(
        "nexus.orchestrator.unified_mcp_gateway.get_account_pool_manager", lambda: None
    )
    monkeypatch.setattr(
        "nexus.orchestrator.unified_mcp_gateway.CrossProcessLeaseCoordinator", Coordinator
    )
    gateway = _gateway(tmp_path)
    job, workspace = _assist_job(
        tmp_path,
        job_kind="model_probe",
        provider="agy",
        status="UNKNOWN_REQUIRES_RECONCILE",
        blocker="ASSIST_ACCOUNT_LEASE_RECONCILIATION_REQUIRED",
        reconciliation_required=True,
        durable_exit_marker=True,
        account_alias_hash="a" * 12,
        account_lease_id_hash="b" * 12,
        account_lease_owner_pid=12345,
        account_lease_released=False,
        account_lease_cleanup_status="RECONCILIATION_REQUIRED",
    )
    workspace.joinpath("partial.txt").unlink()
    workspace.rmdir()
    gateway._assist_write(job)
    group = _FakeGroup()
    monkeypatch.setattr(os, "kill", group.kill)
    monkeypatch.setattr(argv_command, "_live_group_members", group.live_members)
    reconciled = gateway._task_reconcile({"task_id": "t3076"})
    assert reconciled["status"] == "FAILED", reconciled
    assert reconciled["account_lease_cleanup_status"] == "RELEASED"
    assert len(reconciled_leases) == 1
    assert group.sent == []
