"""#2998: the Agy pool stop check sits at the shared lease points, not only in nexus-agy-dispatch.

While the pool is stopped (James 2026-10-30) every lease is refused unless
NEXUS_AGY_POOL_STOPPED_OVERRIDE is exactly "1" -- the switch #2990 put in the
dispatcher.  Here: ``CrossProcessLeaseCoordinator.acquire_claim`` and
``AgyAccountPoolManager.acquire`` (Gateway worker and model probe), and the
shared override name.  The bench path (workforce auto-update ``attest``) is
in tests/benchmark, the ``nexus-hcom-agy-safe`` launch in tests/ops.

The autouse fixture in tests/conftest.py sets the override; these tests
``delenv`` it.  No real account, pool or agy is touched.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from nexus.executors import worker_registry
from nexus.executors.worker_contract import WorkerOutcome
from nexus.executors.worker_registry import AgyWorkerAdapter
from nexus.orchestrator import unified_mcp_gateway as gateway_module
from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService
from nexus.orchestrator.unified_mcp_gateway import GatewayInputError, UnifiedMCPGateway
from nexus.services import agy_account_pool
from nexus.services.agy_account_pool import (
    AgyAccount,
    AgyAccountPoolManager,
    AgyAccountPoolStoppedError,
    CrossProcessLeaseCoordinator,
)

ROOT = Path(__file__).resolve().parents[2]
DISPATCHER = ROOT / "scripts" / "ops" / "nexus-agy-dispatch"
LAUNCHER = ROOT / "scripts" / "ops" / "nexus-hcom-agy-safe"
OVERRIDE = "NEXUS_AGY_POOL_STOPPED_OVERRIDE"


class _Untouchable:
    """A pool manager whose every attribute access fails the test."""

    def __getattr__(self, name: str):
        raise AssertionError(f"pool manager touched while stopped: {name}")


def _coordinator(tmp_path: Path) -> CrossProcessLeaseCoordinator:
    return CrossProcessLeaseCoordinator(
        _Untouchable(),  # type: ignore[arg-type]
        allocator_lock_path=tmp_path / "pool" / "allocator.lock",
        leases_dir=tmp_path / "pool" / "leases",
    )


def test_override_name_is_the_dispatcher_switch() -> None:
    """One switch: the dispatcher (#2990), the pool module and the hcom launcher agree."""
    pattern = re.compile(r'^POOL_STOPPED_OVERRIDE_ENV = "([A-Z_]+)"$', re.M)
    for script in (DISPATCHER, LAUNCHER):
        assert pattern.findall(script.read_text(encoding="utf-8")) == [OVERRIDE]
    assert agy_account_pool.POOL_STOPPED_OVERRIDE_ENV == OVERRIDE


@pytest.mark.parametrize("value", [None, "", "0", "true", "yes", " 1", "1 ", "11"])
def test_pool_counts_as_stopped_unless_override_is_exactly_one(monkeypatch, value) -> None:
    if value is None:
        monkeypatch.delenv(OVERRIDE, raising=False)
    else:
        monkeypatch.setenv(OVERRIDE, value)
    assert agy_account_pool.agy_pool_stopped() is True
    with pytest.raises(AgyAccountPoolStoppedError, match="^AGY_ACCOUNT_POOL_STOPPED: "):
        agy_account_pool.refuse_if_agy_pool_stopped()


def test_override_one_lets_leases_through(monkeypatch) -> None:
    monkeypatch.setenv(OVERRIDE, "1")
    assert agy_account_pool.agy_pool_stopped() is False
    agy_account_pool.refuse_if_agy_pool_stopped()


def test_acquire_claim_refused_before_any_lock_receipt_or_manager_call(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.delenv(OVERRIDE, raising=False)
    coordinator = _coordinator(tmp_path)

    with pytest.raises(AgyAccountPoolStoppedError, match="AGY_ACCOUNT_POOL_STOPPED"):
        coordinator.acquire_claim(consumer_id="bench-x", wait_timeout=0, model_family="gemini")

    assert not (tmp_path / "pool").exists()  # no allocator lock, no leases dir, no receipt


def test_rotate_claim_cannot_lease_a_new_account_while_stopped(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv(OVERRIDE, raising=False)
    coordinator = _coordinator(tmp_path)
    retired: list[str] = []
    monkeypatch.setattr(
        coordinator, "retire_failed_claim", lambda claim, kind, **_kw: retired.append(kind)
    )
    claim = SimpleNamespace(account_alias_hash="h1", lease=SimpleNamespace(consumer_id="c1"))

    with pytest.raises(AgyAccountPoolStoppedError):
        coordinator.rotate_claim(claim, "quota_exhausted", set(), wait_timeout=0)  # type: ignore[arg-type]

    assert retired == ["quota_exhausted"]  # the failed claim is still cleaned up
    assert not (tmp_path / "pool" / "leases").exists()


def test_manager_acquire_refused_before_ensure_active_or_pool(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv(OVERRIDE, raising=False)
    manager = AgyAccountPoolManager([AgyAccount(alias="acc-a", home_dir=str(tmp_path))])

    def forbidden(*_args, **_kwargs):
        raise AssertionError("pool touched while stopped")

    monkeypatch.setattr(manager, "ensure_active", forbidden)
    monkeypatch.setattr(manager, "_refresh_pool_health", forbidden)
    monkeypatch.setattr(manager, "_ensure_pool", forbidden)

    with pytest.raises(AgyAccountPoolStoppedError):
        manager.acquire("task-1")


def test_gateway_model_probe_maps_stopped_pool_to_its_own_blocker(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv(OVERRIDE, raising=False)
    monkeypatch.setenv("NEXUS_AGY_LEASES_DIR", str(tmp_path / "pool" / "leases"))
    monkeypatch.setenv("NEXUS_AGY_ALLOCATOR_LOCK_PATH", str(tmp_path / "pool" / "allocator.lock"))
    monkeypatch.setattr(gateway_module, "get_account_pool_manager", _Untouchable)
    probe = SimpleNamespace(_agy_probe_model_family=UnifiedMCPGateway._agy_probe_model_family)

    with pytest.raises(GatewayInputError, match="^AGY_ACCOUNT_POOL_STOPPED$") as raised:
        UnifiedMCPGateway._acquire_agy_probe_claim(probe, task_id="t1", model="gemini-3.8")  # type: ignore[arg-type]

    assert isinstance(raised.value.__cause__, AgyAccountPoolStoppedError)
    assert not (tmp_path / "pool").exists()


def test_gateway_agy_worker_fails_closed_without_running_agy(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv(OVERRIDE, raising=False)
    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    for name in (
        "NEXUS_AGY_WORKER_MODEL",
        "NEXUS_AGY_ACCOUNT_POOL_ENABLED",
        "NEXUS_AGY_ACCOUNT_ALIASES",
        "NEXUS_AGY_BLOCKED_ACCOUNTS",
        "NEXUS_AGY_PREFERRED_ACCOUNTS",
        "NEXUS_AGY_RESERVE_ACCOUNTS",
        "NEXUS_AGY_FALLBACK_ACCOUNTS",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("nexus.executors.worker_registry.shutil.which", lambda name: "/bin/agy")
    leases = tmp_path / "leases"
    monkeypatch.setenv("NEXUS_AGY_LEASES_DIR", str(leases))
    monkeypatch.setenv("NEXUS_AGY_ALLOCATOR_LOCK_PATH", str(tmp_path / "allocator.lock"))
    gateway_home = tmp_path / "gateway-home"
    gateway_home.mkdir()
    monkeypatch.setenv("HOME", str(gateway_home))
    manager_bin = tmp_path / "pool" / "bin" / "agy-cli-manager"
    manager_bin.parent.mkdir(parents=True)
    manager_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setenv("NEXUS_AGY_ACCOUNT_POOL_MANAGER_PATH", str(manager_bin))
    home = tmp_path / "accounts" / "acc-a"
    (home / ".gemini" / "antigravity-cli").mkdir(parents=True)
    pool = AgyAccountPoolManager([AgyAccount(alias="acc-a", home_dir=str(home))])
    monkeypatch.setattr("nexus.services.agy_account_pool.get_account_pool_manager", lambda: pool)
    monkeypatch.setenv("NEXUS_AGY_PREFERRED_ACCOUNTS", "acc-a")
    ran: list[object] = []
    monkeypatch.setattr(worker_registry, "run_cli_worker", lambda *a, **k: ran.append(a))
    canonical = tmp_path / "canonical"
    canonical.mkdir()
    for args in (
        ["init", "-q"],
        ["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "i"],
    ):
        subprocess.run(["git", *args], cwd=canonical, check=True, capture_output=True)
    target = tmp_path / "target"
    target.mkdir()

    receipt = AgyWorkerAdapter(
        use_installed_account_pool=True, canonical_root=canonical.resolve()
    ).invoke(
        SimpleNamespace(task_id="agy-2998", maximum_provider_calls=1),
        SimpleNamespace(target_worktree=str(target.resolve())),
        prompt="bounded task",
        worker_role="implementation",
        timeout_seconds=60.0,
    )

    assert ran == []
    assert receipt.outcome == WorkerOutcome.FAILED.value
    assert receipt.failure_reason is not None
    assert "AgyAccountPoolStoppedError" in receipt.failure_reason
    assert receipt.provider_calls == 0
    assert not leases.exists() or not any(leases.iterdir())  # no lock, no receipt


class _Service(SelfHostedTaskService):
    def __init__(self, state_dir: Path) -> None:
        self.state_dir = state_dir


def test_gateway_model_probe_submit_refused_before_preflight_record_or_lease(
    monkeypatch, tmp_path
) -> None:
    """Codex r1: the refusal comes before the --version preflight and the probe job record."""
    monkeypatch.delenv(OVERRIDE, raising=False)
    gateway = UnifiedMCPGateway(service=_Service(tmp_path / "state"))
    monkeypatch.setattr(
        gateway, "_provider_executable", lambda provider: ({"default_model": "m"}, "/bin/echo")
    )
    monkeypatch.setattr(gateway_module, "get_account_pool_manager", _Untouchable)
    ran: list[object] = []
    monkeypatch.setattr(gateway_module.subprocess, "run", lambda *a, **k: ran.append(a))
    monkeypatch.setattr(gateway_module.subprocess, "Popen", lambda *a, **k: ran.append(a))
    arguments = {
        "task_id": "probe-2998",
        "provider": "agy",
        "model": "gemini-3.8-flash-medium",
        "prompt": "Return probe JSON",
        "output_schema": {"type": "object"},
    }

    with pytest.raises(GatewayInputError, match="^AGY_ACCOUNT_POOL_STOPPED$"):
        gateway._model_probe_submit(arguments)

    assert ran == []
    assert gateway._assist_read("probe-2998") is None


def test_gateway_agy_worker_with_claimless_injected_pool_refused(monkeypatch, tmp_path) -> None:
    """Codex r1: a pool without acquire() (legacy ensure_active route) leases nothing either."""
    monkeypatch.delenv(OVERRIDE, raising=False)
    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    monkeypatch.setattr("nexus.executors.worker_registry.shutil.which", lambda name: "/bin/agy")
    account = AgyAccount(alias="legacy", home_dir=str(tmp_path / "h1"))

    class _LegacyPool:
        active_account_alias_hash = account.alias_hash

        def ensure_active(self, target_worktree=None):
            raise AssertionError("legacy pool touched while stopped")

        def get_active_account(self):
            raise AssertionError("legacy pool touched while stopped")

    ran: list[object] = []
    monkeypatch.setattr(worker_registry, "run_cli_worker", lambda *a, **k: ran.append(a))

    receipt = AgyWorkerAdapter(account_pool=_LegacyPool()).invoke(
        SimpleNamespace(task_id="agy-2998-legacy"),
        SimpleNamespace(target_worktree=str(tmp_path)),
        prompt="hello",
        worker_role="implementation",
    )

    assert ran == []
    assert receipt.outcome == WorkerOutcome.FAILED.value
    assert receipt.provider_calls == 0
    assert receipt.failure_reason is not None
    assert "AGY_ACCOUNT_POOL_STOPPED" in receipt.failure_reason
