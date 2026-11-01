"""#3076 items 18-20: the gateway removes an assist workspace only when the recorded path is a
real directory directly under the assist workspace parent, only once the provider's process
group is known to be gone, and never while a submit is still starting the provider.

Every test runs with its cwd in a sentinel directory under tmp_path and the assist workspace
parent pointed at tmp_path; each asserts the sentinel survives. No real provider runs: the
provider is a stand-in whose pid is above any pid_max (Linux 2**22, macOS 99999), and
``os.kill``, ``os.killpg``, the group listing and the group termination are replaced, so nothing
is signalled on the host. No live gateway, no Agy, no real lease.
"""

from __future__ import annotations

import os
import signal
import sys
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from nexus.core import argv_command
from nexus.orchestrator.unified_mcp_gateway import UnifiedMCPGateway
from nexus.orchestrator.unified_mcp_gateway_parts import assist_jobs, assist_response, model_probe
from tests.nexus.orchestrator.test_unified_mcp_gateway import FakeService

# Above Linux's largest pid_max (2**22) and macOS's (99999): never a real process.
FAKE_PID = 2**22 + 7321
TASK = "t3076-ws"


class _FakeProvider:
    """A provider Popen stand-in; nothing real behind its pid."""

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
    """os.kill / os.killpg / the group listing for the fake provider's group: the leader is
    gone (a restarted gateway found it dead); ``member_alive`` says whether a member remains."""

    def __init__(self, *, member_alive: bool) -> None:
        self.member_alive = member_alive
        self.sent: list[int] = []

    def kill(self, pid: int, sig: int) -> None:
        assert pid == FAKE_PID, f"os.kill on a pid this test does not own: {pid}"
        if sig != 0:
            self.sent.append(sig)
        raise ProcessLookupError(pid)

    def killpg(self, pgid: int, sig: int) -> None:
        assert pgid == FAKE_PID, f"os.killpg on a group this test does not own: {pgid}"
        self.sent.append(sig)

    def live_members(self, pgid: int) -> list[int]:
        assert pgid == FAKE_PID, f"listing a group this test does not own: {pgid}"
        return [FAKE_PID + 1] if self.member_alive else []


@pytest.fixture
def box(tmp_path, monkeypatch):
    """cwd = a sentinel directory under tmp_path; assist workspace parent = tmp_path/assist-root."""
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
    real_mkdtemp = tempfile.mkdtemp

    def mkdtemp(suffix=None, prefix=None, dir=None):
        # Every workspace a submit creates lands under this test's tmp_path, whatever the code
        # under test asks for.
        return real_mkdtemp(suffix=suffix, prefix=prefix, dir=str(root))

    monkeypatch.setattr(assist_jobs.tempfile, "mkdtemp", mkdtemp)
    service = FakeService()
    service.state_dir = state
    gateway = UnifiedMCPGateway(service=service)
    yield SimpleNamespace(
        tmp=tmp_path, cwd=cwd, sentinel=sentinel, root=root, state=state, gateway=gateway
    )
    assert sentinel.exists(), "the test's cwd lost its sentinel file"


def _job(box, workspace_root, **fields) -> dict:
    job = {
        "schema": "nexus.assisted_provider_job.v1",
        "task_id": TASK,
        "job_id": "assist-3076-ws",
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


def _workspace(parent: Path, name: str = "nexus-assist-t3076-ws-abc") -> Path:
    workspace = parent / name
    workspace.mkdir(parents=True)
    (workspace / "partial.txt").write_text("partial", encoding="utf-8")
    return workspace


# ---------------------------------------------------------------------------
# Item 18: an empty or foreign workspace_root is never removed
# ---------------------------------------------------------------------------


def _case_empty(box):
    return "", [box.sentinel]


def _case_blank(box):
    return "   ", [box.sentinel]


def _case_none(box):
    return None, [box.sentinel]


def _case_dot(box):
    return ".", [box.sentinel]


def _case_relative(box):
    inner = _workspace(box.cwd, "relative-ws")
    return "relative-ws", [inner / "partial.txt"]


def _case_cwd_absolute(box):
    return str(box.cwd), [box.sentinel]


def _case_outside_parent(box):
    outside = _workspace(box.tmp / "elsewhere", "nexus-assist-outside")
    return str(outside), [outside / "partial.txt"]


def _case_nested_below_parent(box):
    nested = _workspace(box.root / "a", "nexus-assist-nested")
    return str(nested), [nested / "partial.txt"]


def _case_symlink_out_of_parent(box):
    target = _workspace(box.tmp / "target", "kept")
    link = box.root / "nexus-assist-link"
    link.symlink_to(target, target_is_directory=True)
    return str(link), [target / "partial.txt"]


def _case_symlink_within_parent(box):
    other = _workspace(box.root, "nexus-assist-other-job")
    link = box.root / "nexus-assist-link"
    link.symlink_to(other, target_is_directory=True)
    return str(link), [other / "partial.txt"]


def _case_parent_itself(box):
    (box.root / "other-job").mkdir()
    return str(box.root), [box.root / "other-job"]


GUARD_CASES = {
    "empty": _case_empty,
    "blank": _case_blank,
    "none": _case_none,
    "dot": _case_dot,
    "relative": _case_relative,
    "cwd_absolute": _case_cwd_absolute,
    "outside_parent": _case_outside_parent,
    "nested_below_parent": _case_nested_below_parent,
    "symlink_out_of_parent": _case_symlink_out_of_parent,
    "symlink_within_parent": _case_symlink_within_parent,
    "parent_itself": _case_parent_itself,
}


@pytest.mark.parametrize("case", sorted(GUARD_CASES))
def test_cleanup_refuses_workspace_root_that_is_not_an_assist_workspace(box, case):
    workspace_root, must_survive = GUARD_CASES[case](box)
    job = _job(box, workspace_root)
    box.gateway._cleanup_assist_workspace(job)
    for path in must_survive:
        assert path.exists(), f"{case}: removed {path} for workspace_root={workspace_root!r}"
    assert box.sentinel.exists(), f"{case}: the cwd was emptied"
    assert job["process_cleanup"] is False, job
    assert job.get("cleanup_error") == "ASSIST_WORKSPACE_ROOT_REFUSED", job


def test_cleanup_refuses_the_cwd_even_under_the_workspace_parent(box, monkeypatch):
    inside = _workspace(box.root, "nexus-assist-cwd")
    monkeypatch.chdir(inside)
    job = _job(box, str(inside))
    box.gateway._cleanup_assist_workspace(job)
    assert (inside / "partial.txt").exists(), "the gateway's own cwd was removed"
    assert job["process_cleanup"] is False
    assert job.get("cleanup_error") == "ASSIST_WORKSPACE_ROOT_REFUSED"


def test_cleanup_removes_a_workspace_directly_under_the_parent(box):
    workspace = _workspace(box.root)
    job = _job(box, str(workspace))
    box.gateway._cleanup_assist_workspace(job)
    assert not workspace.exists()
    assert job["process_cleanup"] is True
    assert "cleanup_error" not in job
    assert job["filesystem_delta"]["created"] == ["partial.txt"]


def test_cleanup_of_an_already_removed_workspace_is_clean(box):
    job = _job(box, str(box.root / "nexus-assist-gone"))
    box.gateway._cleanup_assist_workspace(job)
    assert job["process_cleanup"] is True


def test_cancel_of_never_started_job_with_empty_workspace_root_keeps_the_cwd(box):
    job = _job(box, "", status="SUBMITTED")
    job.pop("pid")
    job.pop("pgid")
    box.gateway._assist_write(job)
    cancelled = box.gateway._assist_cancel(TASK)
    assert box.sentinel.exists(), "cancel emptied the gateway's cwd (workspace_root was empty)"
    assert cancelled["status"] == "CANCELLED", cancelled
    assert cancelled["process_cleanup"] is False


def test_reconcile_with_empty_workspace_root_keeps_the_cwd(box, monkeypatch):
    job = _job(
        box,
        "",
        status="UNKNOWN_REQUIRES_RECONCILE",
        blocker="ASSIST_PROVIDER_PROCESS_LOST",
        reconciliation_required=True,
    )
    box.gateway._assist_write(job)
    group = _FakeGroup(member_alive=False)
    monkeypatch.setattr(os, "kill", group.kill)
    monkeypatch.setattr(argv_command, "_live_group_members", group.live_members)
    reconciled = box.gateway._task_reconcile({"task_id": TASK})
    assert box.sentinel.exists(), "reconcile emptied the gateway's cwd (workspace_root was empty)"
    assert reconciled["process_cleanup"] is False
    assert group.sent == []


def test_reconcile_with_empty_workspace_root_still_waits_for_the_group(box, monkeypatch):
    """An empty workspace_root says nothing about the workspace being gone: the group check
    still applies (#3076 item 18, caller side)."""
    job = _job(
        box,
        "",
        status="UNKNOWN_REQUIRES_RECONCILE",
        blocker="ASSIST_PROVIDER_PROCESS_LOST",
        reconciliation_required=True,
    )
    box.gateway._assist_write(job)
    group = _FakeGroup(member_alive=True)
    monkeypatch.setattr(os, "kill", group.kill)
    monkeypatch.setattr(argv_command, "_live_group_members", group.live_members)
    reconciled = box.gateway._task_reconcile({"task_id": TASK})
    assert box.sentinel.exists()
    assert reconciled["status"] == "UNKNOWN_REQUIRES_RECONCILE", reconciled
    assert reconciled["reconciliation_required"] is True


def test_cancel_of_reconcile_pending_job_with_empty_workspace_root_keeps_the_cwd(box, monkeypatch):
    """An empty root used to read as "workspace gone" (skipping the group check), then
    ``Path("")`` named the cwd and was removed (#3076 item 18)."""
    job = _job(
        box,
        "",
        status="UNKNOWN_REQUIRES_RECONCILE",
        blocker="ASSIST_PROVIDER_PROCESS_LOST",
        reconciliation_required=True,
    )
    box.gateway._assist_write(job)
    group = _FakeGroup(member_alive=False)
    monkeypatch.setattr(os, "kill", group.kill)
    monkeypatch.setattr(os, "killpg", group.killpg)
    monkeypatch.setattr(argv_command, "_live_group_members", group.live_members)
    cancelled = box.gateway._assist_cancel(TASK)
    assert box.sentinel.exists(), "cancel emptied the gateway's cwd (workspace_root was empty)"
    assert cancelled["status"] == "CANCELLED", cancelled
    assert cancelled["process_cleanup"] is False
    assert group.sent == []


# ---------------------------------------------------------------------------
# Item 19: completion after a gateway restart waits for the provider's group
# ---------------------------------------------------------------------------


def _restarted_job(box, workspace_root: str) -> dict:
    """A provider that exited with a durable exit marker, seen by a gateway that restarted
    since: the provider is not registered in this process and its leader is gone."""
    return _job(box, workspace_root, durable_exit_marker=True, exit_code=0)


def test_restart_completion_keeps_workspace_while_group_has_a_member(box, monkeypatch):
    workspace = _workspace(box.root)
    box.gateway._assist_write(_restarted_job(box, str(workspace)))
    group = _FakeGroup(member_alive=True)
    monkeypatch.setattr(os, "kill", group.kill)
    monkeypatch.setattr(os, "killpg", group.killpg)
    monkeypatch.setattr(argv_command, "_live_group_members", group.live_members)
    refreshed = box.gateway._assist_refresh(TASK)
    assert refreshed is not None
    assert workspace.exists(), (
        "the post-restart completion removed the workspace while a member of the provider's "
        "group was still alive"
    )
    assert refreshed["status"] == "UNKNOWN_REQUIRES_RECONCILE", refreshed
    assert refreshed["blocker"] == "ASSIST_PROVIDER_GROUP_CLEANUP_INCOMPLETE"
    assert refreshed["reconciliation_required"] is True
    assert refreshed["process_cleanup"] is False
    assert group.sent == [], "a group this gateway does not hold must not be signalled here"
    again = box.gateway._assist_refresh(TASK)
    assert again is not None and again["status"] == "UNKNOWN_REQUIRES_RECONCILE"
    assert workspace.exists()


def test_restart_completion_keeps_workspace_when_group_cannot_be_listed(box, monkeypatch):
    workspace = _workspace(box.root)
    box.gateway._assist_write(_restarted_job(box, str(workspace)))
    group = _FakeGroup(member_alive=False)
    monkeypatch.setattr(os, "kill", group.kill)
    monkeypatch.setattr(argv_command, "_live_group_members", lambda pgid: None)
    refreshed = box.gateway._assist_refresh(TASK)
    assert refreshed is not None
    assert workspace.exists()
    assert refreshed["status"] == "UNKNOWN_REQUIRES_RECONCILE", refreshed


def test_restart_completion_removes_workspace_once_group_is_empty(box, monkeypatch):
    workspace = _workspace(box.root)
    box.gateway._assist_write(_restarted_job(box, str(workspace)))
    group = _FakeGroup(member_alive=False)
    monkeypatch.setattr(os, "kill", group.kill)
    monkeypatch.setattr(argv_command, "_live_group_members", group.live_members)
    refreshed = box.gateway._assist_refresh(TASK)
    assert refreshed is not None
    assert refreshed["status"] in {"COMPLETED", "FAILED"}, refreshed
    assert refreshed["exit_code"] == 0
    assert refreshed["process_cleanup"] is True
    assert not workspace.exists()
    assert group.sent == []


def test_restart_completion_with_empty_workspace_root_keeps_the_cwd(box, monkeypatch):
    box.gateway._assist_write(_restarted_job(box, ""))
    group = _FakeGroup(member_alive=False)
    monkeypatch.setattr(os, "kill", group.kill)
    monkeypatch.setattr(argv_command, "_live_group_members", group.live_members)
    refreshed = box.gateway._assist_refresh(TASK)
    assert refreshed is not None
    assert box.sentinel.exists(), "the post-restart completion emptied the gateway's cwd"
    assert refreshed["process_cleanup"] is False


# ---------------------------------------------------------------------------
# Item 20: a cancel that arrives while the submit is starting the provider
# ---------------------------------------------------------------------------


def _patch_launch(box, monkeypatch, on_popen):
    executable = box.tmp / "cline-stub"
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    executable.chmod(0o755)
    monkeypatch.setenv("NEXUS_CLINE_BIN", str(executable))
    monkeypatch.setattr("nexus.orchestrator.unified_mcp_gateway._git", lambda *a, **k: "a" * 40)
    monkeypatch.setattr(
        "nexus.orchestrator.unified_mcp_gateway.pre_action_guard", lambda *a, **k: None
    )
    monkeypatch.setattr(assist_jobs, "require_child_stays_unreaped", lambda: None)
    terminated: list = []

    def terminate(process):
        assert process.pid == FAKE_PID
        terminated.append(process)
        return True

    monkeypatch.setattr(assist_jobs, "_terminate_provider_group", terminate)
    # The fake provider is never seen as exited and its group never listed for real.
    monkeypatch.setattr(assist_response, "kill_group_if_exited", lambda process: False)
    monkeypatch.setattr(argv_command, "_live_group_members", lambda pgid: [FAKE_PID])
    real_popen = assist_jobs.subprocess.Popen

    def popen(command, *args, **kwargs):
        if not kwargs.get("start_new_session"):
            return real_popen(command, *args, **kwargs)
        return on_popen(Path(kwargs["cwd"]))

    monkeypatch.setattr(assist_jobs.subprocess, "Popen", popen)
    return terminated


def _submit_args() -> dict:
    return {
        "task_id": TASK,
        "what": "assist",
        "why": "assist",
        "allowed_files": ["README.md"],
        "provider": "cline",
    }


def test_cancel_while_submit_starts_the_provider_keeps_workspace_and_is_honoured(box, monkeypatch):
    seen: dict = {}

    def on_popen(workspace: Path) -> _FakeProvider:
        # A cancel request arrives after the SUBMITTED record was written, before the pid is.
        seen["cancel"] = box.gateway._assist_cancel(TASK)
        seen["workspace_after_cancel"] = workspace.exists()
        seen["workspace"] = workspace
        return _FakeProvider()

    terminated = _patch_launch(box, monkeypatch, on_popen)
    result = box.gateway._assist_submit(_submit_args())
    assert seen["workspace_after_cancel"], (
        "a cancel that arrived before the submit recorded the pid removed the workspace the "
        "provider was being started in"
    )
    assert seen["cancel"]["status"] == "SUBMITTED", seen["cancel"]
    assert seen["cancel"]["blocker"] == "ASSIST_CANCEL_PENDING_LAUNCH"
    assert len(terminated) == 1, "the cancel request was lost: the started provider kept running"
    assert result["status"] == "CANCELLED", result
    assert result["blocker"] == "ASSIST_CANCELLED"
    assert result["pid"] == FAKE_PID
    assert result["process_cleanup"] is True
    assert not seen["workspace"].exists()
    record = box.gateway._assist_read(TASK)
    assert record is not None and record["status"] == "CANCELLED"
    assert TASK not in box.gateway._model_probe_inflight()


def test_cancel_while_retry_starts_the_provider_keeps_workspace_and_is_honoured(box, monkeypatch):
    def fail_start(workspace: Path):
        raise OSError("provider could not start")

    _patch_launch(box, monkeypatch, fail_start)
    failed = box.gateway._assist_submit(_submit_args())
    assert failed["status"] == "FAILED", failed

    seen: dict = {}

    def on_popen(workspace: Path) -> _FakeProvider:
        seen["cancel"] = box.gateway._assist_cancel(TASK)
        seen["workspace_after_cancel"] = workspace.exists()
        seen["workspace"] = workspace
        return _FakeProvider()

    terminated = _patch_launch(box, monkeypatch, on_popen)
    result = box.gateway._assist_retry(TASK)
    assert seen["workspace_after_cancel"], (
        "a cancel that arrived before the retry recorded the pid removed the new workspace"
    )
    assert seen["cancel"]["blocker"] == "ASSIST_CANCEL_PENDING_LAUNCH"
    assert len(terminated) == 1
    assert result["status"] == "CANCELLED", result
    assert not seen["workspace"].exists()


def test_cancel_while_model_probe_starts_the_provider_keeps_workspace_and_is_honoured(
    box, monkeypatch
):
    from nexus.orchestrator.unified_mcp_gateway_parts import model_probe

    seen: dict = {}

    def on_popen(workspace: Path) -> _FakeProvider:
        seen["cancel"] = box.gateway._assist_cancel(TASK)
        seen["workspace_after_cancel"] = workspace.exists()
        seen["workspace"] = workspace
        return _FakeProvider()

    terminated = _patch_launch(box, monkeypatch, on_popen)
    monkeypatch.setattr(model_probe, "require_child_stays_unreaped", lambda: None)
    monkeypatch.setattr(
        box.gateway,
        "_provider_executable",
        lambda provider: ({"default_model": "glm-5.2"}, "/bin/echo"),
    )
    monkeypatch.setattr(
        "nexus.orchestrator.unified_mcp_gateway.subprocess.run",
        lambda command, **kwargs: SimpleNamespace(returncode=0, stdout="cline 1.0.0\n", stderr=""),
    )
    result = box.gateway._model_probe_submit({
        "task_id": TASK,
        "provider": "cline",
        "model": "glm-5.2",
        "prompt": "probe",
        "output_schema": {"type": "object"},
    })
    assert seen["workspace_after_cancel"], (
        "a cancel that arrived before the probe recorded the pid removed its workspace"
    )
    assert seen["cancel"]["blocker"] == "ASSIST_CANCEL_PENDING_LAUNCH"
    assert len(terminated) == 1
    assert result["status"] == "CANCELLED", result
    assert not seen["workspace"].exists()
    assert TASK not in box.gateway._model_probe_inflight()


def test_cancel_between_record_and_launch_keeps_workspace_and_cancel_survives(box, monkeypatch):
    """Same window with a caller-supplied action envelope: the provider is started in a
    workspace that still exists, and the record ends CANCELLED, not overwritten as RUNNING."""
    seen: dict = {}

    def on_popen(workspace: Path) -> _FakeProvider:
        seen["cancel"] = box.gateway._assist_cancel(TASK)
        seen["cwd_exists_at_launch"] = workspace.exists()
        return _FakeProvider()

    _patch_launch(box, monkeypatch, on_popen)
    box.gateway._assist_submit(
        {"task_id": TASK, "what": "w", "why": "y", "allowed_files": ["a.py"]},
        action={"action_id": "a1", "attempt_id": "t1"},
    )
    assert seen["cwd_exists_at_launch"], "the provider was started in a removed workspace"
    assert seen["cancel"]["status"] != "CANCELLED", "cancel reported done before the pid existed"
    final = box.gateway._assist_read(TASK)
    assert final is not None and final["status"] == "CANCELLED", final


def test_failed_start_after_a_pending_cancel_leaves_no_request_behind(box, monkeypatch):
    def on_popen(workspace: Path):
        box.gateway._assist_cancel(TASK)
        raise OSError("provider could not start")

    _patch_launch(box, monkeypatch, on_popen)
    result = box.gateway._assist_submit(_submit_args())
    assert result["status"] == "FAILED", result
    assert TASK not in box.gateway._model_probe_inflight()
    assert TASK not in getattr(box.gateway, "_assist_cancel_request_ids", set())


def test_cancel_of_a_stale_never_started_job_still_removes_its_workspace(box):
    """No submit in this gateway owns the record (e.g. it ended before Popen): no provider can
    be starting, so the job is cancelled and its workspace removed, as before."""
    workspace = _workspace(box.root)
    job = _job(box, str(workspace), status="SUBMITTED")
    job.pop("pid")
    job.pop("pgid")
    box.gateway._assist_write(job)
    cancelled = box.gateway._assist_cancel(TASK)
    assert cancelled["status"] == "CANCELLED", cancelled
    assert cancelled["process_cleanup"] is True
    assert not workspace.exists()


# ---------------------------------------------------------------------------
# Residual of item 20 (burn 11/01): one launch per task id
# ---------------------------------------------------------------------------


def _pause_in_flight_checks(box, monkeypatch, names: tuple[str, str]) -> None:
    """After both launches passed their own existence check (both are at the command
    builder), each launch's next record read, the one its in-flight check makes, waits briefly
    for the other's: if the check is not taken under the lock both see an empty slot."""
    gateway = box.gateway
    at_command = threading.Barrier(2, timeout=10)
    reached = {name: threading.Event() for name in names}
    armed: set[str] = set()
    real_command = gateway._assist_command
    real_read = gateway._assist_read

    def command(*args, **kwargs):
        at_command.wait()
        armed.add(threading.current_thread().name)
        return real_command(*args, **kwargs)

    def read(task_id):
        name = threading.current_thread().name
        if name in armed:
            armed.discard(name)
            reached[name].set()
            other = next(other for other in names if other != name)
            reached[other].wait(0.5)
        return real_read(task_id)

    monkeypatch.setattr(gateway, "_assist_command", command)
    monkeypatch.setattr(gateway, "_assist_read", read)


def _run_concurrently(calls: dict) -> dict:
    results: dict = {}

    def run(name, call):
        try:
            results[name] = call()
        except Exception as exc:  # noqa: BLE001 - asserted by the caller
            results[name] = exc

    threads = [
        threading.Thread(target=run, args=(name, call), name=name) for name, call in calls.items()
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(20)
    assert not any(thread.is_alive() for thread in threads)
    return results


def _assert_one_launch_one_refusal(box, popens: list, results: dict) -> None:
    assert len(popens) == 1, f"two providers started for one task_id: {popens}"
    refused = [value for value in results.values() if isinstance(value, Exception)]
    assert len(refused) == 1, results
    assert "ASSIST_DUPLICATE_LAUNCH_REFUSED" in str(refused[0])
    started = next(value for value in results.values() if isinstance(value, dict))
    assert started["status"] == "RUNNING", started
    assert TASK not in box.gateway._model_probe_inflight()
    # Only the started provider's workspace remains; the refused launch removed its empty one.
    assert [path.name for path in box.root.iterdir()] == [Path(popens[0]).name]


def test_concurrent_submits_of_one_task_start_one_provider(box, monkeypatch):
    popens: list = []

    def on_popen(workspace: Path) -> _FakeProvider:
        popens.append(str(workspace))
        return _FakeProvider()

    _patch_launch(box, monkeypatch, on_popen)
    _pause_in_flight_checks(box, monkeypatch, ("A", "B"))
    results = _run_concurrently({
        "A": lambda: box.gateway._assist_submit(_submit_args()),
        "B": lambda: box.gateway._assist_submit(_submit_args()),
    })
    _assert_one_launch_one_refusal(box, popens, results)


def _failed_submit(box, monkeypatch) -> dict:
    def fail_start(workspace: Path):
        raise OSError("provider could not start")

    _patch_launch(box, monkeypatch, fail_start)
    failed = box.gateway._assist_submit(_submit_args())
    assert failed["status"] == "FAILED", failed
    return failed


def test_concurrent_retries_of_one_task_start_one_provider(box, monkeypatch):
    _failed_submit(box, monkeypatch)
    popens: list = []

    def on_popen(workspace: Path) -> _FakeProvider:
        popens.append(str(workspace))
        return _FakeProvider()

    _patch_launch(box, monkeypatch, on_popen)
    _pause_in_flight_checks(box, monkeypatch, ("A", "B"))
    results = _run_concurrently({
        "A": lambda: box.gateway._assist_retry(TASK),
        "B": lambda: box.gateway._assist_retry(TASK),
    })
    _assert_one_launch_one_refusal(box, popens, results)


def _hold_second_until_first_done(box, monkeypatch) -> threading.Event:
    """Both launches pass their own existence check; B then waits until A has finished."""
    gateway = box.gateway
    at_command = threading.Barrier(2, timeout=10)
    a_done = threading.Event()
    real_command = gateway._assist_command

    def command(*args, **kwargs):
        at_command.wait()
        if threading.current_thread().name == "B":
            assert a_done.wait(10)
        return real_command(*args, **kwargs)

    monkeypatch.setattr(gateway, "_assist_command", command)
    return a_done


def _run_a_then_b(call, a_done: threading.Event) -> dict:
    """A, then B once A has finished (B waits in the command builder, see above)."""

    def first():
        try:
            return call()
        finally:
            a_done.set()

    return _run_concurrently({"A": first, "B": call})


def test_submit_that_lost_the_race_to_a_finished_submit_starts_nothing(box, monkeypatch):
    popens: list = []

    def on_popen(workspace: Path) -> _FakeProvider:
        popens.append(str(workspace))
        return _FakeProvider()

    _patch_launch(box, monkeypatch, on_popen)
    a_done = _hold_second_until_first_done(box, monkeypatch)
    results = _run_a_then_b(lambda: box.gateway._assist_submit(_submit_args()), a_done)
    _assert_one_launch_one_refusal(box, popens, results)
    assert isinstance(results["B"], Exception), results


def test_retry_that_lost_the_race_to_a_finished_retry_starts_nothing(box, monkeypatch):
    _failed_submit(box, monkeypatch)
    popens: list = []

    def on_popen(workspace: Path) -> _FakeProvider:
        popens.append(str(workspace))
        return _FakeProvider()

    _patch_launch(box, monkeypatch, on_popen)
    a_done = _hold_second_until_first_done(box, monkeypatch)
    results = _run_a_then_b(lambda: box.gateway._assist_retry(TASK), a_done)
    _assert_one_launch_one_refusal(box, popens, results)
    assert isinstance(results["B"], Exception), results


def test_a_finished_launch_leaves_a_later_launch_of_the_task_in_flight(box, monkeypatch):
    """The submit is cancelled and retried right after it wrote its pid, before it returned:
    when the submit then returns it must not take the retry's in-flight entry, or a cancel
    during the retry's launch removes the retry's workspace."""
    gateway = box.gateway
    retry_at_popen = threading.Event()
    submit_returned = threading.Event()
    seen: dict = {}
    retry_results: dict = {}
    armed = [True]

    def on_popen(workspace: Path) -> _FakeProvider:
        if threading.current_thread().name == "retry":
            retry_at_popen.set()
            assert submit_returned.wait(10)
            seen["inflight_during_retry_launch"] = TASK in gateway._model_probe_inflight()
            seen["cancel"] = gateway._assist_cancel(TASK)
            seen["retry_workspace_after_cancel"] = workspace.exists()
        return _FakeProvider()

    _patch_launch(box, monkeypatch, on_popen)
    real_response = gateway._assist_response

    def response(job, *, operation):
        if operation == "submit" and armed:
            armed.clear()
            cancelled = gateway._assist_cancel(TASK)
            assert cancelled["status"] == "CANCELLED", cancelled

            def run_retry():
                try:
                    retry_results["retry"] = gateway._assist_retry(TASK)
                except Exception as exc:  # noqa: BLE001 - asserted below
                    retry_results["retry"] = exc

            retry_results["thread"] = threading.Thread(target=run_retry, name="retry")
            retry_results["thread"].start()
            assert retry_at_popen.wait(10)
        return real_response(job, operation=operation)

    monkeypatch.setattr(gateway, "_assist_response", response)
    gateway._assist_submit(_submit_args())
    submit_returned.set()
    retry_results["thread"].join(20)
    assert not retry_results["thread"].is_alive()
    assert seen["inflight_during_retry_launch"], (
        "the submit cleared the in-flight entry of the retry still starting its provider"
    )
    assert seen["cancel"]["blocker"] == "ASSIST_CANCEL_PENDING_LAUNCH", seen["cancel"]
    assert seen["retry_workspace_after_cancel"], "a cancel removed the retry's workspace mid-launch"
    assert retry_results["retry"]["status"] == "CANCELLED", retry_results["retry"]


# ---------------------------------------------------------------------------
# Residual of item 20 (burn 11/01): the model probe keeps one launch per task id too
# ---------------------------------------------------------------------------


def _patch_probe(box, monkeypatch, on_popen, on_version=None) -> list:
    """The probe launches through the same stubbed Popen; its provider is /bin/echo (never run)
    and each ``--version`` preflight returns a fixed version after calling ``on_version``."""
    terminated = _patch_launch(box, monkeypatch, on_popen)
    monkeypatch.setattr(model_probe, "require_child_stays_unreaped", lambda: None)
    monkeypatch.setattr(model_probe, "_terminate_provider_group", lambda process: True)
    monkeypatch.setattr(
        box.gateway,
        "_provider_executable",
        lambda provider: ({"default_model": "glm-5.2"}, "/bin/echo"),
    )
    versions: list = []

    def run(command, **kwargs):
        assert command[1:] == ["--version"], command
        versions.append(command)
        if on_version is not None:
            on_version(len(versions))
        return SimpleNamespace(returncode=0, stdout="cline 1.0.0\n", stderr="")

    monkeypatch.setattr(model_probe.subprocess, "run", run)
    return terminated


def _probe_args() -> dict:
    return {
        "task_id": TASK,
        "provider": "cline",
        "model": "glm-5.2",
        "prompt": "probe",
        "output_schema": {"type": "object"},
    }


def test_probe_leaves_an_assist_launched_during_its_preflight_running(box, monkeypatch):
    popens: list = []
    launched: dict = {}

    def on_popen(workspace: Path) -> _FakeProvider:
        popens.append(workspace)
        return _FakeProvider()

    def on_version(count: int) -> None:
        # Meanwhile an assist submit of the same task id starts its provider.
        if count == 1:
            launched["assist"] = box.gateway._assist_submit(_submit_args())

    _patch_probe(box, monkeypatch, on_popen, on_version)
    with pytest.raises(Exception, match="MODEL_PROBE_SUBMIT_IN_PROGRESS"):
        box.gateway._model_probe_submit(_probe_args())
    assert launched["assist"]["status"] == "RUNNING", launched["assist"]
    record = box.gateway._assist_read(TASK)
    assert record is not None
    assert record["job_kind"] == "assist", record
    assert record["pid"] == FAKE_PID
    assert record["workspace_root"] == launched["assist"]["workspace_root"]
    assert box.gateway._assist_processes[TASK].pid == FAKE_PID
    # One provider started; the refused probe created no workspace of its own.
    assert len(popens) == 1, popens
    assert [path.name for path in box.root.iterdir()] == [popens[0].name]
    assert TASK not in box.gateway._model_probe_inflight()


class _LockWithEntryHook:
    """The gateway's assist lock, calling ``hook(caller)`` before each entry."""

    def __init__(self, lock, hook) -> None:
        self._lock = lock
        self._hook = hook

    def __enter__(self):
        self._hook(sys._getframe(1).f_code.co_name)
        return self._lock.__enter__()

    def __exit__(self, *exc):
        return self._lock.__exit__(*exc)

    def acquire(self, *args, **kwargs):
        return self._lock.acquire(*args, **kwargs)

    def release(self):
        return self._lock.release()


def test_probe_keeps_an_assist_record_written_before_it_takes_the_lock(box, monkeypatch):
    """The probe's record check and its in-flight entry are one step under the lock: a record
    another launch wrote after the probe's first look, just before the probe took the lock,
    is found and kept."""
    popens: list = []
    workspace = _workspace(box.root)
    assist_job = _job(box, str(workspace), status="FAILED", pid=None, pgid=None)

    def on_popen(path: Path) -> _FakeProvider:
        popens.append(path)
        return _FakeProvider()

    _patch_probe(box, monkeypatch, on_popen)
    written: list = []

    def hook(caller: str) -> None:
        if caller == "_model_probe_submit_guarded" and not written:
            written.append(box.gateway._assist_write(dict(assist_job)))

    monkeypatch.setattr(
        box.gateway, "_assist_lock", _LockWithEntryHook(box.gateway._assist_lock, hook)
    )
    with pytest.raises(Exception, match="MODEL_PROBE_SUBMIT_IN_PROGRESS"):
        box.gateway._model_probe_submit(_probe_args())
    assert written, "the probe never took the lock for its in-flight entry"
    record = box.gateway._assist_read(TASK)
    assert record is not None
    assert record["job_kind"] == "assist", record
    assert record["job_id"] == assist_job["job_id"]
    assert record["workspace_root"] == str(workspace)
    assert popens == []
    assert [path.name for path in box.root.iterdir()] == [workspace.name]
    assert TASK not in box.gateway._model_probe_inflight()


def test_finished_probe_leaves_a_later_launch_of_the_task_in_flight(box, monkeypatch):
    """A later launch of the task id (here a retry entering the in-flight set after the probe
    wrote its pid, before the probe returned) keeps its entry and ownership when the probe
    returns, so a cancel during that launch still only leaves a request."""
    gateway = box.gateway
    later = {"job_id": "assist-later", "workspace_root": str(box.root / "absent")}
    _patch_probe(box, monkeypatch, lambda workspace: _FakeProvider())
    real_publish = gateway._assist_publish_launch

    def publish(task_id, job, process, *, operation):
        response = real_publish(task_id, job, process, operation=operation)
        gateway._assist_launch_begin(task_id, later, retried=gateway._assist_read(task_id))
        return response

    monkeypatch.setattr(gateway, "_assist_publish_launch", publish)
    result = gateway._model_probe_submit(_probe_args())
    assert result["status"] == "RUNNING", result
    assert TASK in gateway._model_probe_inflight(), (
        "the finished probe cleared the in-flight entry of a later launch of its task id"
    )
    assert gateway._assist_launch_owners().get(TASK) == "assist-later"
    gateway._assist_launch_end(TASK, "assist-later")
    assert TASK not in gateway._model_probe_inflight()


def test_probe_whose_provider_did_not_start_leaves_the_in_flight_set(box, monkeypatch):
    def on_popen(workspace: Path) -> _FakeProvider:
        raise OSError("provider could not start")

    _patch_probe(box, monkeypatch, on_popen)
    result = box.gateway._model_probe_submit(_probe_args())
    assert result["status"] == "FAILED", result
    assert result["blocker"] == "ASSIST_PROVIDER_FAILED", result
    assert TASK not in box.gateway._model_probe_inflight()
    assert TASK not in box.gateway._assist_launch_owners()


# ---------------------------------------------------------------------------
# A query or cancel acts only on the job it read: a retry of the same task id that launched in
# between keeps its record and its registered provider (#3076)
# ---------------------------------------------------------------------------


def _interleave_retry_at(box, monkeypatch, caller: str, entry: int, before) -> dict:
    """Run a retry of the task, after ``before()``, just before ``caller`` enters the assist
    lock for the ``entry``-th time; returns the retry's response under "retry"."""
    gateway = box.gateway
    state: dict = {"seen": 0, "retry": None}

    def hook(name: str) -> None:
        if state["retry"] is not None or name != caller:
            return
        state["seen"] += 1
        if state["seen"] == entry:
            before()
            state["retry"] = {}
            state["retry"] = gateway._assist_retry(TASK)

    monkeypatch.setattr(gateway, "_assist_lock", _LockWithEntryHook(gateway._assist_lock, hook))
    return state


def _launch_old_job(box, monkeypatch):
    old_provider = _FakeProvider()
    terminated = _patch_launch(box, monkeypatch, lambda workspace: old_provider)
    first = box.gateway._assist_submit(_submit_args())
    assert first["status"] == "RUNNING", first
    new_provider = _FakeProvider()
    monkeypatch.setattr(assist_jobs.subprocess, "Popen", lambda *a, **k: new_provider)
    examined: list = []

    def exited(process) -> bool:
        examined.append(process)
        return process.returncode is not None

    monkeypatch.setattr(assist_response, "kill_group_if_exited", exited)
    return first["job_id"], old_provider, new_provider, terminated, examined


def _assert_retry_untouched(box, state, new_provider) -> None:
    retry = state["retry"]
    assert retry, "the retry never ran at the chosen point"
    assert retry["status"] == "RUNNING", retry
    assert box.gateway._assist_processes.get(TASK) is new_provider, (
        "the retry's provider is no longer registered"
    )
    record = box.gateway._assist_read(TASK)
    assert record is not None
    assert (record["job_id"], record["status"]) == (retry["job_id"], "RUNNING"), record


@pytest.mark.parametrize(
    ("caller", "entry", "exited_first"),
    [
        ("_assist_refresh", 1, True),  # before the provider lookup
        ("_assist_refresh", 2, True),  # before the finished provider is unregistered
        ("_assist_write_current", 1, False),  # before a still-running job's record is written
    ],
)
def test_query_of_a_job_leaves_a_retry_launched_meanwhile_tracked(
    box, monkeypatch, caller, entry, exited_first
):
    old_job_id, old_provider, new_provider, _, examined = _launch_old_job(box, monkeypatch)

    def old_provider_exits() -> None:
        old_provider.returncode = 1

    if exited_first:
        old_provider_exits()
    state = _interleave_retry_at(box, monkeypatch, caller, entry, old_provider_exits)
    result = box.gateway._assist_refresh(TASK)
    assert result is not None and result["job_id"] == old_job_id, result
    _assert_retry_untouched(box, state, new_provider)
    assert new_provider not in examined, "the query settled the retry's provider as its own"


@pytest.mark.parametrize(
    ("caller", "entry"),
    [
        ("_assist_cancel", 1),  # before the provider lookup
        ("_assist_cancel", 2),  # after the old provider was terminated, before it is unregistered
        ("_assist_write_current", 1),  # before the cancel's query writes the job as running
    ],
)
def test_cancel_leaves_a_retry_launched_meanwhile_tracked_and_unsignalled(
    box, monkeypatch, caller, entry
):
    old_job_id, old_provider, new_provider, terminated, _ = _launch_old_job(box, monkeypatch)

    def old_provider_exits() -> None:
        old_provider.returncode = -signal.SIGTERM

    state = _interleave_retry_at(box, monkeypatch, caller, entry, old_provider_exits)
    result = box.gateway._assist_cancel(TASK)
    assert result["job_id"] == old_job_id, result
    assert new_provider not in terminated, "the cancel signalled the retry's provider"
    _assert_retry_untouched(box, state, new_provider)


def test_query_still_finishes_and_unregisters_its_own_job(box, monkeypatch):
    old_job_id, old_provider, _, _, _ = _launch_old_job(box, monkeypatch)
    old_provider.returncode = 1
    result = box.gateway._assist_refresh(TASK)
    assert result is not None and result["status"] == "FAILED", result
    assert TASK not in box.gateway._assist_processes
    record = box.gateway._assist_read(TASK)
    assert record is not None
    assert (record["job_id"], record["status"]) == (old_job_id, "FAILED"), record


def test_cancel_still_terminates_unregisters_and_records_its_own_job(box, monkeypatch):
    old_job_id, old_provider, _, terminated, _ = _launch_old_job(box, monkeypatch)
    result = box.gateway._assist_cancel(TASK)
    assert terminated == [old_provider]
    assert result["status"] == "CANCELLED", result
    assert result["blocker"] == "ASSIST_CANCELLED", result
    assert TASK not in box.gateway._assist_processes
    record = box.gateway._assist_read(TASK)
    assert record is not None
    assert (record["job_id"], record["status"]) == (old_job_id, "CANCELLED"), record


def test_query_holding_its_own_job_for_reconciliation_unregisters_its_provider(box, monkeypatch):
    old_job_id, _, _, _, _ = _launch_old_job(box, monkeypatch)

    def group_unlistable(process) -> bool:
        raise PermissionError("group cannot be listed")

    monkeypatch.setattr(assist_response, "kill_group_if_exited", group_unlistable)
    result = box.gateway._assist_refresh(TASK)
    assert result is not None, result
    assert result["blocker"] == "ASSIST_PROVIDER_GROUP_CLEANUP_INCOMPLETE", result
    assert TASK not in box.gateway._assist_processes
    record = box.gateway._assist_read(TASK)
    assert record is not None
    assert (record["job_id"], record["status"]) == (old_job_id, "UNKNOWN_REQUIRES_RECONCILE")


def _replace_with_newer_job(box, workspace: Path) -> _FakeProvider:
    """What a reconciliation followed by a retry leaves behind: a newer job of the task id, with
    its own workspace and registered provider."""
    newer = _FakeProvider()
    newer_job = _job(box, str(workspace), job_id="assist-newer", status="RUNNING")
    with box.gateway._assist_lock:
        box.gateway._assist_processes[TASK] = newer
        box.gateway._assist_write(newer_job)
    return newer


def _assert_newer_job_untouched(box, newer, newer_workspace: Path) -> None:
    record = box.gateway._assist_read(TASK)
    assert record is not None
    assert (record["job_id"], record["status"]) == ("assist-newer", "RUNNING"), record
    assert box.gateway._assist_processes.get(TASK) is newer
    assert newer_workspace.exists(), "the cancel removed the newer job's workspace"


def test_cancel_of_a_reconcile_pending_job_leaves_a_retry_after_reconcile_recorded(
    box, monkeypatch
):
    """The cancel reads a job a restarted gateway lost track of; while it removes that job's
    workspace, a reconcile settles the job and a retry starts a new provider. The cancel
    records its own job only while the record is still that job's."""
    gateway = box.gateway
    old_job_id, _, new_provider, terminated, _ = _launch_old_job(box, monkeypatch)
    gateway._assist_processes.pop(TASK)  # a restarted gateway holds no provider
    group = _FakeGroup(member_alive=False)
    monkeypatch.setattr(os, "kill", group.kill)
    monkeypatch.setattr(os, "killpg", group.killpg)
    monkeypatch.setattr(argv_command, "_live_group_members", group.live_members)
    real_cleanup = gateway._cleanup_assist_workspace
    state: dict = {}

    def cleanup_then_reconcile_and_retry(job) -> None:
        real_cleanup(job)
        if "retry" not in state:
            state["retry"] = {}
            state["reconcile"] = gateway._task_reconcile({"task_id": TASK})
            state["retry"] = gateway._assist_retry(TASK)

    monkeypatch.setattr(gateway, "_cleanup_assist_workspace", cleanup_then_reconcile_and_retry)
    result = gateway._assist_cancel(TASK)
    assert (result["job_id"], result["status"]) == (old_job_id, "CANCELLED"), result
    assert terminated == [] and group.sent == []
    _assert_retry_untouched(box, state, new_provider)


def test_cancel_releasing_a_finished_job_lease_leaves_a_newer_job_recorded(box, monkeypatch):
    newer_workspace = _workspace(box.root, "nexus-retry-t3076-ws-new")
    box.gateway._assist_write(
        _job(
            box,
            "",
            status="FAILED",
            pid=None,
            pgid=None,
            account_lease_id_hash="lease-old",
            account_lease_released=False,
        )
    )
    real_release = box.gateway._release_assist_account_claim
    state: dict = {}

    def release_then_newer_job(task_id, job) -> bool:
        released = real_release(task_id, job)
        state["newer"] = _replace_with_newer_job(box, newer_workspace)
        return released

    monkeypatch.setattr(box.gateway, "_release_assist_account_claim", release_then_newer_job)
    result = box.gateway._assist_cancel(TASK)
    assert "newer" in state, "the cancel never reached the lease release"
    assert (result["job_id"], result["status"]) == ("assist-3076-ws", "FAILED"), result
    _assert_newer_job_untouched(box, state["newer"], newer_workspace)


def test_query_whose_record_vanished_neither_recreates_it_nor_unregisters(box, monkeypatch):
    _, old_provider, _, _, _ = _launch_old_job(box, monkeypatch)

    def record_removed_then_exited(process) -> bool:
        box.gateway._assist_path(TASK).unlink()
        process.returncode = 1
        return True

    monkeypatch.setattr(assist_response, "kill_group_if_exited", record_removed_then_exited)
    result = box.gateway._assist_refresh(TASK)
    assert result is not None and result["status"] == "FAILED", result
    assert box.gateway._assist_read(TASK) is None, "the query recreated a removed record"
    assert box.gateway._assist_processes.get(TASK) is old_provider


def test_query_held_for_reconciliation_leaves_a_newer_job_tracked(box, monkeypatch):
    """The query's own provider group cannot be listed (the job is held for reconciliation);
    by then a newer job of the task id has its record and provider, which the hold keeps."""
    old_job_id, _, _, _, _ = _launch_old_job(box, monkeypatch)
    newer_workspace = _workspace(box.root, "nexus-retry-t3076-ws-new")
    state: dict = {}

    def newer_job_then_unlistable(process) -> bool:
        state["newer"] = _replace_with_newer_job(box, newer_workspace)
        raise PermissionError("group cannot be listed")

    monkeypatch.setattr(assist_response, "kill_group_if_exited", newer_job_then_unlistable)
    result = box.gateway._assist_refresh(TASK)
    assert result is not None and result["job_id"] == old_job_id, result
    assert result["blocker"] == "ASSIST_PROVIDER_GROUP_CLEANUP_INCOMPLETE", result
    _assert_newer_job_untouched(box, state["newer"], newer_workspace)


# ---------------------------------------------------------------------------
# A reconcile records only the job it read: a retry recorded after the reconcile read the job
# keeps its record, provider and workspace, and the reconcile reports the job it read (#3076)
# ---------------------------------------------------------------------------

# One case per reconcile record write: (group member alive, lease receipt result, expected
# (status, blocker) of the job the reconcile read)
_RECONCILE_WRITES = [
    pytest.param(
        True,
        None,
        ("UNKNOWN_REQUIRES_RECONCILE", "ASSIST_PROVIDER_GROUP_CLEANUP_INCOMPLETE"),
        id="group-still-running",
    ),
    pytest.param(
        False,
        "LEASE_BUSY_PRESERVED",
        ("UNKNOWN_REQUIRES_RECONCILE", "ASSIST_ACCOUNT_LEASE_RECONCILIATION_REQUIRED"),
        id="lease-preserved",
    ),
    pytest.param(
        False, "LEASE_RECEIPT_REMOVED", ("FAILED", "ASSIST_PROVIDER_PROCESS_LOST"), id="settled"
    ),
]


def _reconcile_pending_job(box, monkeypatch, *, member_alive: bool, lease_result):
    """A job a query held for reconciliation (its group could not be listed), optionally with
    an account lease; the group listing and the lease coordinator are stand-ins."""
    from nexus.orchestrator import unified_mcp_gateway as gateway_module

    workspace = _workspace(box.root)
    fields: dict = {
        "status": "UNKNOWN_REQUIRES_RECONCILE",
        "blocker": "ASSIST_PROVIDER_GROUP_CLEANUP_INCOMPLETE",
        "reconciliation_required": True,
    }
    if lease_result is not None:
        fields.update({
            "account_alias_hash": "alias-old",
            "account_lease_id_hash": "lease-old",
            "account_lease_owner_pid": FAKE_PID,
            "account_lease_released": False,
        })
    box.gateway._assist_write(_job(box, str(workspace), **fields))
    group = _FakeGroup(member_alive=member_alive)
    monkeypatch.setattr(os, "kill", group.kill)
    monkeypatch.setattr(os, "killpg", group.killpg)
    monkeypatch.setattr(argv_command, "_live_group_members", group.live_members)
    lease_calls: list = []

    class _Coordinator:
        def __init__(self, _manager=None) -> None:
            pass

        def reconcile_claim_receipt(self, **claim) -> dict:
            lease_calls.append(claim)
            return {"result": lease_result}

    monkeypatch.setattr(gateway_module, "CrossProcessLeaseCoordinator", _Coordinator)
    monkeypatch.setattr(gateway_module, "get_account_pool_manager", lambda: None)
    return workspace, group, lease_calls


def _assert_lease_calls_name_only_the_read_job(lease_calls: list, lease_result) -> None:
    expected = (
        []
        if lease_result is None
        else [
            {"account_alias_hash": "alias-old", "lease_id_hash": "lease-old", "owner_pid": FAKE_PID}
        ]
    )
    assert lease_calls == expected, lease_calls


@pytest.mark.parametrize(("member_alive", "lease_result", "expected"), _RECONCILE_WRITES)
def test_reconcile_leaves_a_retry_recorded_after_its_read_tracked(
    box, monkeypatch, member_alive, lease_result, expected
):
    """Just before the reconcile's record write takes the assist lock, another reconcile has
    settled the job and a retry recorded a newer job with its own provider and workspace."""
    workspace, group, lease_calls = _reconcile_pending_job(
        box, monkeypatch, member_alive=member_alive, lease_result=lease_result
    )
    newer_workspace = _workspace(box.root, "nexus-retry-t3076-ws-new")
    state: dict = {}

    def hook(name: str) -> None:
        # hook <- __enter__ <- the helper taking the lock <- its caller
        if name == "_assist_write_current" and sys._getframe(3).f_code.co_name == "_task_reconcile":
            if "newer" not in state:
                state["newer"] = _replace_with_newer_job(box, newer_workspace)

    monkeypatch.setattr(
        box.gateway, "_assist_lock", _LockWithEntryHook(box.gateway._assist_lock, hook)
    )
    result = box.gateway._task_reconcile({"task_id": TASK})
    assert "newer" in state, "the reconcile wrote its record without checking it under the lock"
    assert (result["job_id"], result["status"], result["blocker"]) == (
        "assist-3076-ws",
        *expected,
    ), result
    _assert_newer_job_untouched(box, state["newer"], newer_workspace)
    assert group.sent == [], "the reconcile signalled a process group"
    _assert_lease_calls_name_only_the_read_job(lease_calls, lease_result)
    # Only the read job's own workspace is ever removed, and only once it is settled.
    assert workspace.exists() is (expected[0] != "FAILED")


@pytest.mark.parametrize(("member_alive", "lease_result", "expected"), _RECONCILE_WRITES)
def test_reconcile_still_records_its_own_job(
    box, monkeypatch, member_alive, lease_result, expected
):
    workspace, group, lease_calls = _reconcile_pending_job(
        box, monkeypatch, member_alive=member_alive, lease_result=lease_result
    )
    result = box.gateway._task_reconcile({"task_id": TASK})
    record = box.gateway._assist_read(TASK)
    assert record is not None
    assert (record["job_id"], record["status"], record["blocker"]) == ("assist-3076-ws", *expected)
    assert (result["job_id"], result["status"]) == (record["job_id"], record["status"]), result
    assert record["reconciliation_required"] is (expected[0] != "FAILED"), record
    assert group.sent == []
    _assert_lease_calls_name_only_the_read_job(lease_calls, lease_result)
    settled = expected[0] == "FAILED"
    assert workspace.exists() is not settled
    if settled:
        assert (record["account_lease_released"], record["process_cleanup"]) == (True, True)


# ---------------------------------------------------------------------------
# A settled record stays settled: once another reconcile, cancel or query of the same job has
# recorded it as COMPLETED, FAILED or CANCELLED without reconciliation, a write based on an
# earlier read neither reopens it nor replaces its outcome (#3076)
# ---------------------------------------------------------------------------


def _settle_before_write_from(box, monkeypatch, caller: str, settled: dict) -> dict:
    """Just before ``caller``'s record write takes the assist lock, another call of the same job
    records it with ``settled`` (same job id); returns that settled record under "settled"."""
    state: dict = {}

    def hook(name: str) -> None:
        # hook <- __enter__ <- _assist_write_current <- its caller
        if name == "_assist_write_current" and sys._getframe(3).f_code.co_name == caller:
            if "settled" not in state:
                record = dict(box.gateway._assist_read(TASK))
                record.update(settled)
                state["settled"] = box.gateway._assist_write(record)

    monkeypatch.setattr(
        box.gateway, "_assist_lock", _LockWithEntryHook(box.gateway._assist_lock, hook)
    )
    return state


def _assert_settled_record_kept(box, state: dict, result: dict) -> None:
    assert "settled" in state, "the call wrote its record without checking it under the lock"
    expected = state["settled"]
    record = box.gateway._assist_read(TASK)
    assert record is not None
    assert (record["job_id"], record["status"], record["blocker"]) == (
        expected["job_id"],
        expected["status"],
        expected["blocker"],
    ), record
    assert not record.get("reconciliation_required"), record
    assert (result["job_id"], result["status"]) == (expected["job_id"], expected["status"]), result


_SETTLED_BY_RECONCILE = {
    "status": "FAILED",
    "blocker": "ASSIST_PROVIDER_PROCESS_LOST",
    "reconciliation_required": False,
}
_SETTLED_BY_CANCEL = {
    "status": "CANCELLED",
    "blocker": "ASSIST_CANCELLED",
    "reconciliation_required": False,
}


@pytest.mark.parametrize(
    "settled", [_SETTLED_BY_RECONCILE, _SETTLED_BY_CANCEL], ids=["reconciled", "cancelled"]
)
@pytest.mark.parametrize(("member_alive", "lease_result", "expected"), _RECONCILE_WRITES)
def test_reconcile_keeps_a_job_settled_after_its_read(
    box, monkeypatch, member_alive, lease_result, expected, settled
):
    _reconcile_pending_job(box, monkeypatch, member_alive=member_alive, lease_result=lease_result)
    state = _settle_before_write_from(box, monkeypatch, "_task_reconcile", settled)
    result = box.gateway._task_reconcile({"task_id": TASK})
    _assert_settled_record_kept(box, state, result)


@pytest.mark.parametrize("member_alive", [True, False], ids=["group-still-running", "group-gone"])
def test_cancel_of_a_reconcile_pending_job_keeps_it_settled_after_its_read(
    box, monkeypatch, member_alive
):
    _reconcile_pending_job(box, monkeypatch, member_alive=member_alive, lease_result=None)
    state = _settle_before_write_from(box, monkeypatch, "_assist_cancel", _SETTLED_BY_RECONCILE)
    result = box.gateway._assist_cancel(TASK)
    _assert_settled_record_kept(box, state, result)


def test_cancel_of_a_running_job_keeps_the_outcome_a_query_recorded_meanwhile(box, monkeypatch):
    _launch_old_job(box, monkeypatch)
    completed = {"status": "COMPLETED", "blocker": None, "reconciliation_required": False}
    state = _settle_before_write_from(box, monkeypatch, "_assist_cancel", completed)
    result = box.gateway._assist_cancel(TASK)
    _assert_settled_record_kept(box, state, result)


def test_query_keeps_a_job_settled_after_its_read(box, monkeypatch):
    """The query finds the provider gone without an exit marker (it would ask for
    reconciliation); a reconcile settled the job after the query read it."""
    box.gateway._assist_write(_job(box, str(_workspace(box.root))))
    group = _FakeGroup(member_alive=False)
    monkeypatch.setattr(os, "kill", group.kill)
    state = _settle_before_write_from(box, monkeypatch, "_assist_refresh", _SETTLED_BY_RECONCILE)
    result = box.gateway._assist_refresh(TASK)
    assert result is not None
    _assert_settled_record_kept(box, state, result)


def test_cancel_still_records_the_lease_release_of_a_settled_job(box, monkeypatch):
    box.gateway._assist_write(
        _job(
            box,
            "",
            pid=None,
            pgid=None,
            account_lease_id_hash="lease-old",
            account_lease_released=False,
            **_SETTLED_BY_RECONCILE,
        )
    )

    def release(task_id, job) -> bool:
        job.update({"account_lease_released": True, "account_lease_cleanup_status": "RELEASED"})
        return True

    monkeypatch.setattr(box.gateway, "_release_assist_account_claim", release)
    result = box.gateway._assist_cancel(TASK)
    record = box.gateway._assist_read(TASK)
    assert record is not None
    assert (record["status"], record["account_lease_released"]) == ("FAILED", True), record
    assert (result["job_id"], result["status"]) == ("assist-3076-ws", "FAILED"), result


_UNSETTLED = {"status": "UNKNOWN_REQUIRES_RECONCILE", "reconciliation_required": True}


# (record on disk, record written, whether the write lands)
_SETTLED_WRITES = [
    pytest.param(_SETTLED_BY_RECONCILE, _UNSETTLED, False, id="settled-not-reopened"),
    pytest.param(
        _SETTLED_BY_CANCEL,
        {**_SETTLED_BY_CANCEL, "reconciliation_required": True},
        False,
        id="settled-not-marked-for-reconciliation",
    ),
    pytest.param(
        {"status": "COMPLETED", "blocker": None, "reconciliation_required": False},
        _SETTLED_BY_CANCEL,
        False,
        id="settled-outcome-not-replaced",
    ),
    pytest.param(
        {**_SETTLED_BY_RECONCILE, "account_lease_released": False},
        {**_SETTLED_BY_RECONCILE, "account_lease_released": True},
        True,
        id="same-outcome-updated",
    ),
    pytest.param(
        {**_SETTLED_BY_RECONCILE, "account_lease_released": True},
        {**_SETTLED_BY_RECONCILE, "account_lease_released": False},
        False,
        id="same-outcome-lease-release-kept",
    ),
    pytest.param(_UNSETTLED, _SETTLED_BY_RECONCILE, True, id="unsettled-settled"),
    pytest.param(
        {**_SETTLED_BY_CANCEL, "reconciliation_required": True},
        _SETTLED_BY_RECONCILE,
        True,
        id="pending-cancel-reconciled",
    ),
    pytest.param({"status": "RUNNING"}, _UNSETTLED, True, id="running-held"),
]


@pytest.mark.parametrize(("on_disk", "written", "lands"), _SETTLED_WRITES)
def test_record_write_of_the_same_job_keeps_a_settled_record(box, on_disk, written, lands):
    stored = box.gateway._assist_write(_job(box, "", **on_disk))
    job = _job(box, "", **written)
    result = box.gateway._assist_write_current(TASK, job)
    record = box.gateway._assist_read(TASK)
    assert record is not None
    expected = {**stored, **written} if lands else stored
    for key in ("status", "blocker", "reconciliation_required", "account_lease_released"):
        assert record.get(key) == expected.get(key), (key, record)
    assert result.get("status") == expected.get("status"), result


# ---------------------------------------------------------------------------
# A lease release recorded once stays recorded: a later write of the same job by a call that
# found the account claim already gone does not record it as unreleased (#3144)
# ---------------------------------------------------------------------------


class _Claim:
    """An Agy account claim stand-in that counts its releases; no real lease behind it."""

    def __init__(self) -> None:
        self.releases = 0

    def release(self) -> None:
        self.releases += 1

    def abandon_parent_reference(self) -> None:
        raise AssertionError("the claim was abandoned instead of released")


def _hold_a_lease(box, claim: _Claim) -> None:
    record = box.gateway._assist_read(TASK)
    assert record is not None
    record.update({"account_lease_id_hash": "lease-3144", "account_lease_released": False})
    box.gateway._assist_write(record)
    box.gateway._assist_account_claims[TASK] = claim


def _assert_lease_recorded_released_and_retry_allowed(box, claim: _Claim, job_id: str) -> None:
    assert claim.releases == 1, claim.releases
    record = box.gateway._assist_read(TASK)
    assert record is not None
    assert record["job_id"] == job_id, record
    assert (record["account_lease_released"], record["account_lease_cleanup_status"]) == (
        True,
        "RELEASED",
    ), record
    assert not record.get("reconciliation_required"), record
    retry = box.gateway._assist_retry(TASK)
    assert retry["status"] == "RUNNING", retry


def test_second_cancel_of_a_finished_job_keeps_the_lease_release_of_the_first(box, monkeypatch):
    """Two cancels read the same FAILED job with an unreleased lease; the first releases the
    claim and records it while the second is between its read and its claim lookup."""
    failed = _failed_submit(box, monkeypatch)
    claim = _Claim()
    _hold_a_lease(box, claim)
    monkeypatch.setattr(assist_jobs.subprocess, "Popen", lambda *a, **k: _FakeProvider())
    state: dict = {}

    def hook(caller: str) -> None:
        if caller == "_release_assist_account_claim" and "first" not in state:
            state["first"] = {}
            state["first"] = box.gateway._assist_cancel(TASK)

    monkeypatch.setattr(
        box.gateway, "_assist_lock", _LockWithEntryHook(box.gateway._assist_lock, hook)
    )
    second = box.gateway._assist_cancel(TASK)
    assert state.get("first"), "the first cancel never ran inside the second"
    for result in (state["first"], second):
        assert (result["status"], result["account_lease_released"]) == ("FAILED", True), result
    _assert_lease_recorded_released_and_retry_allowed(box, claim, failed["job_id"])


def test_query_outcome_written_after_a_cancel_released_the_lease_records_the_release(
    box, monkeypatch
):
    """A query finishing the job and a cancel of it run together: the cancel releases the
    claim, the query (finding no claim) records FAILED first, then the cancel's CANCELLED write
    is refused. The query's outcome is kept and the cancel's lease release is recorded."""
    old_job_id, old_provider, _, terminated, _ = _launch_old_job(box, monkeypatch)
    claim = _Claim()
    _hold_a_lease(box, claim)
    # The query (this thread) sees the provider exit; the cancel's own query does not.
    monkeypatch.setattr(
        assist_response,
        "kill_group_if_exited",
        lambda process: threading.current_thread() is threading.main_thread(),
    )
    cancel_terminating = threading.Event()
    query_settled = threading.Event()
    cancel_writing = threading.Event()
    query_done = threading.Event()

    def terminate(process) -> bool:
        terminated.append(process)
        cancel_terminating.set()
        assert query_settled.wait(10), "the query never reached its lease release"
        return True

    monkeypatch.setattr(assist_jobs, "_terminate_provider_group", terminate)

    def hook(caller: str) -> None:
        on_main = threading.current_thread() is threading.main_thread()
        if on_main and caller == "_release_assist_account_claim":
            query_settled.set()
            assert cancel_writing.wait(10), "the cancel never reached its record write"
        elif not on_main and caller == "_assist_write_current":
            if sys._getframe(3).f_code.co_name == "_assist_cancel":
                cancel_writing.set()
                assert query_done.wait(10), "the query never finished"

    monkeypatch.setattr(
        box.gateway, "_assist_lock", _LockWithEntryHook(box.gateway._assist_lock, hook)
    )
    results: dict = {}

    def cancel_job() -> None:
        results["cancel"] = box.gateway._assist_cancel(TASK)

    cancel = threading.Thread(target=cancel_job)
    cancel.start()
    assert cancel_terminating.wait(10), "the cancel never reached the provider termination"
    old_provider.returncode = 1
    query = box.gateway._assist_refresh(TASK)
    query_done.set()
    cancel.join(20)
    assert not cancel.is_alive()
    assert query is not None and query["status"] == "FAILED", query
    assert terminated == [old_provider]
    assert (results["cancel"]["job_id"], results["cancel"]["status"]) == (old_job_id, "FAILED")
    assert results["cancel"]["account_lease_released"] is True, results["cancel"]
    record = box.gateway._assist_read(TASK)
    assert record is not None and record["status"] == "FAILED", record
    _assert_lease_recorded_released_and_retry_allowed(box, claim, old_job_id)


def test_refused_write_of_a_released_lease_keeps_the_settled_outcome(box):
    stored = box.gateway._assist_write(
        _job(box, "", account_lease_released=False, **_SETTLED_BY_CANCEL)
    )
    job = _job(
        box,
        "",
        account_lease_released=True,
        account_lease_cleanup_status="RELEASED",
        **_SETTLED_BY_RECONCILE,
    )
    result = box.gateway._assist_write_current(TASK, job)
    record = box.gateway._assist_read(TASK)
    assert record is not None
    for key in ("status", "blocker", "reconciliation_required"):
        assert record.get(key) == stored.get(key), (key, record)
    assert (record["account_lease_released"], record["account_lease_cleanup_status"]) == (
        True,
        "RELEASED",
    ), record
    assert result == record
