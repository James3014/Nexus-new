"""#2716: an Agy model probe waits a bounded time for a free pool account.

Uses the real ``CrossProcessLeaseCoordinator`` (per-account flocks in a temp
leases dir) with a one-account fake manager, so "busy" is a real held lease.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from nexus.orchestrator import unified_mcp_gateway as gateway_module
from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService
from nexus.orchestrator.unified_mcp_gateway import UnifiedMCPGateway
from nexus.orchestrator.unified_mcp_gateway_parts import model_probe
from nexus.services.agy_account_pool import (
    AgyAccount,
    AgyAccountPoolManager,
    CrossProcessLeaseCoordinator,
)

MODEL = "gemini-3.8-flash-medium"


class _Service(SelfHostedTaskService):
    def __init__(self, state_dir: Path) -> None:
        self.state_dir = state_dir


class _FakePopen:
    pid = 55301

    def __init__(self, command, *, stdout, stderr, env=None, pass_fds=(), **kwargs):
        stdout.write(
            json.dumps({
                "conversation_id": "pool-wait-probe",
                "status": "SUCCESS",
                "response": json.dumps({"probe": "ok"}),
            })
        )
        stdout.flush()

    def poll(self):
        return 0


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(model_probe.MODEL_PROBE_POOL_WAIT_ENV, raising=False)
    monkeypatch.delenv("NEXUS_AGY_BLOCKED_ACCOUNTS", raising=False)
    home = tmp_path / "home-a"
    home.mkdir()
    manager = AgyAccountPoolManager(
        accounts=[AgyAccount(alias="a", home_dir=str(home))], use_real_manager=False
    )

    def coordinator(_manager=None) -> CrossProcessLeaseCoordinator:
        return CrossProcessLeaseCoordinator(
            manager=manager,
            allocator_lock_path=tmp_path / "allocator.lock",
            leases_dir=tmp_path / "leases",
            poll_interval=0.05,
        )

    gateway = UnifiedMCPGateway(service=_Service(tmp_path / "state"))
    monkeypatch.setattr(
        gateway, "_provider_executable", lambda provider: ({"default_model": MODEL}, "/bin/echo")
    )
    monkeypatch.setattr(gateway_module, "get_account_pool_manager", lambda: manager)
    monkeypatch.setattr(gateway_module, "CrossProcessLeaseCoordinator", coordinator)
    monkeypatch.setattr(gateway_module.subprocess, "Popen", _FakePopen)
    monkeypatch.setattr(gateway_module, "_git", lambda *args, **kwargs: "a" * 40)

    def fake_run(command, **kwargs):
        return SimpleNamespace(returncode=0, stdout="agy 1.4.2\n", stderr="")

    monkeypatch.setattr(gateway_module.subprocess, "run", fake_run)
    return SimpleNamespace(gateway=gateway, coordinator=coordinator, monkeypatch=monkeypatch)


def _args(task_id: str) -> dict:
    return {
        "task_id": task_id,
        "provider": "agy",
        "model": MODEL,
        "prompt": "Return probe JSON",
        "output_schema": {"type": "object", "required": ["probe"]},
    }


def test_busy_pool_that_frees_within_the_wait_completes(env) -> None:
    env.monkeypatch.setenv(model_probe.MODEL_PROBE_POOL_WAIT_ENV, "10")
    holder = env.coordinator().acquire_claim("desktop-holder", wait_timeout=0)
    timer = threading.Timer(0.6, holder.release)
    timer.start()
    try:
        submitted = env.gateway._model_probe_submit(_args("pool-wait-frees"))
    finally:
        timer.join()
    assert submitted["status"] == "RUNNING"
    assert submitted["account_pool_wait_budget_seconds"] == 10.0
    assert submitted["account_pool_wait_ms"] >= 400
    result = env.gateway._assist_refresh("pool-wait-frees")
    assert result["status"] == "COMPLETED"
    assert result["model_response_verified"] is True
    assert result["account_lease_released"] is True


def test_busy_pool_that_never_frees_fails_with_the_same_blocker(env) -> None:
    env.monkeypatch.setenv(model_probe.MODEL_PROBE_POOL_WAIT_ENV, "0.5")
    holder = env.coordinator().acquire_claim("desktop-holder", wait_timeout=0)
    try:
        started = time.monotonic()
        result = env.gateway._model_probe_submit(_args("pool-wait-busy"))
        elapsed = time.monotonic() - started
    finally:
        holder.release()
    assert result["status"] == "FAILED"
    assert result["blocker"] == "AGY_ACCOUNT_POOL_BUSY"
    assert result["account_pool_wait_budget_seconds"] == 0.5
    assert result["account_pool_wait_ms"] >= 400
    assert 0.4 <= elapsed < 5
    assert "account_alias_hash" not in result or result["account_alias_hash"] is None


def test_refresh_and_duplicate_submit_during_the_wait_do_not_touch_the_record(env) -> None:
    env.monkeypatch.setenv(model_probe.MODEL_PROBE_POOL_WAIT_ENV, "10")
    holder = env.coordinator().acquire_claim("desktop-holder", wait_timeout=0)
    out: dict = {}

    def submit() -> None:
        out["result"] = env.gateway._model_probe_submit(_args("pool-wait-refresh"))

    thread = threading.Thread(target=submit)
    thread.start()
    try:
        deadline = time.monotonic() + 5
        while env.gateway._assist_read("pool-wait-refresh") is None:
            assert time.monotonic() < deadline
            time.sleep(0.02)
        while "account_pool_wait_started_at" not in (
            env.gateway._assist_read("pool-wait-refresh") or {}
        ):
            assert time.monotonic() < deadline
            time.sleep(0.02)
        during = env.gateway._assist_refresh("pool-wait-refresh")
        assert during["status"] == "SUBMITTED"
        duplicate = env.gateway._model_probe_submit(_args("pool-wait-refresh"))
        assert duplicate["status"] == "SUBMITTED"
        assert env.gateway._assist_read("pool-wait-refresh")["status"] == "SUBMITTED"
    finally:
        holder.release()
        thread.join(timeout=15)
    assert out["result"]["status"] == "RUNNING"
    final = env.gateway._assist_refresh("pool-wait-refresh")
    assert final["status"] == "COMPLETED"


def test_wait_interrupted_by_restart_fails_without_effect(env) -> None:
    record = {
        "schema": "nexus.assisted_provider_job.v1",
        "job_kind": "model_probe",
        "task_id": "pool-wait-restart",
        "status": "SUBMITTED",
        "provider": "agy",
        "account_pool_wait_started_at": "2026-10-19T00:00:00+00:00",
        "account_pool_wait_budget_seconds": 90.0,
    }
    env.gateway._assist_write(record)
    result = env.gateway._assist_refresh("pool-wait-restart")
    assert result["status"] == "FAILED"
    assert result["blocker"] == "AGY_ACCOUNT_POOL_WAIT_INTERRUPTED"
    assert result["model_response_verified"] is False


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, 90.0),
        ("", 90.0),
        ("abc", 90.0),
        ("nan", 90.0),
        ("inf", 90.0),
        ("-5", 0.0),
        ("30", 30.0),
        ("9999", 300.0),
    ],
)
def test_pool_wait_budget_is_bounded(monkeypatch, raw, expected) -> None:
    if raw is None:
        monkeypatch.delenv(model_probe.MODEL_PROBE_POOL_WAIT_ENV, raising=False)
    else:
        monkeypatch.setenv(model_probe.MODEL_PROBE_POOL_WAIT_ENV, raw)
    assert model_probe.model_probe_pool_wait_seconds() == expected
