"""#3187: while a cancel terminates the provider and before it writes CANCELLED, a concurrent
wait, cancel or query reports the job as still live (not process-lost or provider-failed), and
the cancel settles once, with the provider unregistered in the final write and the lease
released once. The concurrent calls are made from inside the provider termination stand-in
(deterministic, no sleeps). No real provider, signal or lease."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from nexus.orchestrator.unified_mcp_gateway import UnifiedMCPGateway
from nexus.orchestrator.unified_mcp_gateway_parts import assist_jobs, assist_response
from tests.nexus.orchestrator.test_unified_mcp_gateway import FakeService

TASK = "t3187"
FAKE_PID = 2**22 + 3187


class _Provider:
    def __init__(self) -> None:
        self.pid = FAKE_PID
        self.returncode = None


@pytest.fixture
def box(tmp_path, monkeypatch):
    root = tmp_path / "assist-root"
    root.mkdir()
    state = tmp_path / "state"
    state.mkdir()
    monkeypatch.setattr(assist_response, "ASSIST_WORKSPACE_PARENT", str(root), raising=False)
    service = FakeService()
    service.state_dir = state
    gateway = UnifiedMCPGateway(service=service)
    workspace = root / "nexus-assist-t3187-abc"
    workspace.mkdir()
    gateway._assist_write({
        "schema": "nexus.assisted_provider_job.v1",
        "task_id": TASK,
        "job_id": "assist-3187",
        "job_kind": "assist",
        "status": "RUNNING",
        "provider": "cline",
        "pid": FAKE_PID,
        "pgid": FAKE_PID,
        "workspace_mode": "isolated",
        "workspace_root": str(workspace),
        "filesystem_before": {},
        "stdout_artifact": str(state / "out.txt"),
        "stderr_artifact": str(state / "err.txt"),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "attempt_history": [],
        "account_lease_id_hash": "h3187",
    })
    provider = _Provider()
    gateway._assist_processes[TASK] = provider
    seen: list[dict] = []
    releases: list[str] = []

    def terminate(process) -> bool:
        process.returncode = -9  # the provider is gone; the cancel has not written yet
        seen.append(gateway._assist_response(gateway._assist_refresh(TASK), operation="wait"))
        seen.append(gateway._assist_cancel(TASK))  # a concurrent cancel
        seen.append(gateway._assist_response(gateway._assist_refresh(TASK), operation="status"))
        return True

    def release(task_id, job) -> bool:
        releases.append(task_id)
        job.update({"account_lease_released": True, "account_lease_cleanup_status": "RELEASED"})
        return True

    monkeypatch.setattr(assist_jobs, "_terminate_provider_group", terminate)
    monkeypatch.setattr(
        assist_response, "_settle_provider_group", lambda job, p: (True, True, False)
    )
    monkeypatch.setattr(gateway, "_release_assist_account_claim", release)
    return SimpleNamespace(gateway=gateway, seen=seen, releases=releases)


def test_concurrent_callers_see_a_live_job_and_the_cancel_settles_once(box):
    final = box.gateway._assist_cancel(TASK)
    assert len(box.seen) == 3
    for response in box.seen:
        assert response["status"] not in {"FAILED", "UNKNOWN_REQUIRES_RECONCILE", "COMPLETED"}, (
            response
        )
        assert response.get("blocker") != "ASSIST_PROVIDER_PROCESS_LOST", response
    assert final["status"] == "CANCELLED"
    assert box.gateway._assist_read(TASK)["status"] == "CANCELLED"
    assert box.releases == [TASK]
    assert TASK not in box.gateway._assist_processes
    assert TASK not in box.gateway._assist_cancelling_ids()


def test_provider_stays_registered_until_the_cancelled_write(box, monkeypatch):
    registered_at_release: list[bool] = []
    real_release = box.gateway._release_assist_account_claim

    def release(task_id, job) -> bool:
        registered_at_release.append(task_id in box.gateway._assist_processes)
        return real_release(task_id, job)

    monkeypatch.setattr(box.gateway, "_release_assist_account_claim", release)
    box.gateway._assist_cancel(TASK)
    assert registered_at_release == [True]
    assert TASK not in box.gateway._assist_processes
