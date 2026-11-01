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
import tempfile
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
