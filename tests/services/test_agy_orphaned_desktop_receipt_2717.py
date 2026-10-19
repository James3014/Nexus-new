"""#2717: foreground desktop dispatches must not leave lease receipts behind.

* ``acquire_claim`` reclaims a ``desktop-`` receipt only when the account flock
  is free and the owner PID is provably dead; every other case stays fail-closed.
* The provider inherits the lease lock (``pass_fds``), so a free lock proves no
  provider outlived the dispatcher.
* SIGTERM/SIGHUP on a foreground dispatch unwinds through cleanup and releases
  the receipt.
"""

from __future__ import annotations

import fcntl
import json
import os
import signal
import subprocess
import sys
import threading
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
DISPATCH_PATH = ROOT / "scripts" / "ops" / "nexus-agy-dispatch"
os.environ["NEXUS_AGY_SNAPSHOT"] = str(ROOT)
dispatch = SourceFileLoader("nexus_agy_dispatch_2717", str(DISPATCH_PATH)).load_module()

from nexus.services.agy_account_pool import (  # noqa: E402
    AgyAccount,
    AgyAccountPoolBusyError,
    AgyAccountPoolManager,
    CrossProcessLeaseCoordinator,
)

GEMINI = "gemini-3.8-flash-high"


def _dead_pid() -> int:
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    return proc.pid


def _coordinator(tmp_path: Path) -> tuple[CrossProcessLeaseCoordinator, str]:
    home = tmp_path / "home-a"
    home.mkdir(exist_ok=True)
    manager = AgyAccountPoolManager(
        accounts=[AgyAccount(alias="a", home_dir=str(home))], use_real_manager=False
    )
    coordinator = CrossProcessLeaseCoordinator(
        manager=manager,
        allocator_lock_path=tmp_path / "allocator.lock",
        leases_dir=tmp_path / "leases",
        default_wait_timeout=0,
    )
    (tmp_path / "leases").mkdir(exist_ok=True)
    return coordinator, manager._accounts[0].alias_hash


def _write_receipt(tmp_path: Path, alias_hash: str, **fields) -> Path:
    receipt = tmp_path / "leases" / f"{alias_hash}.receipt.json"
    data = {
        "account_alias_hash": alias_hash,
        "lease_id_hash": "deadbeef0001",
        "consumer_id": "desktop-" + "0" * 32,
        "pid": _dead_pid(),
    }
    data.update(fields)
    receipt.write_text(json.dumps(data) + "\n", encoding="utf-8")
    return receipt


def test_dead_desktop_receipt_is_reclaimed(tmp_path: Path) -> None:
    coordinator, alias_hash = _coordinator(tmp_path)
    old = _write_receipt(tmp_path, alias_hash)
    claim = coordinator.acquire_claim("desktop-new", wait_timeout=0)
    try:
        assert claim.account_alias_hash == alias_hash
        new = json.loads(old.read_text(encoding="utf-8"))
        assert new["consumer_id"] == "desktop-new"
        assert new["pid"] == os.getpid()
    finally:
        claim.release()
    assert not old.exists()


@pytest.mark.parametrize(
    "fields",
    [
        pytest.param({"pid": os.getpid()}, id="live-pid"),
        pytest.param({"consumer_id": "model-probe:task-1"}, id="non-desktop-consumer"),
        pytest.param({"consumer_id": "worker:task-1"}, id="worker-consumer"),
        pytest.param({"account_alias_hash": "000000000000"}, id="identity-mismatch"),
        pytest.param({"pid": "123"}, id="pid-not-int"),
        pytest.param({"pid": True}, id="pid-bool"),
        pytest.param({"pid": 0}, id="pid-zero"),
    ],
)
def test_ambiguous_receipts_stay_fail_closed(tmp_path: Path, fields: dict) -> None:
    coordinator, alias_hash = _coordinator(tmp_path)
    receipt = _write_receipt(tmp_path, alias_hash, **fields)
    before = receipt.read_text(encoding="utf-8")
    with pytest.raises(AgyAccountPoolBusyError):
        coordinator.acquire_claim("desktop-new", wait_timeout=0)
    assert receipt.read_text(encoding="utf-8") == before


def test_unreadable_receipt_stays_fail_closed(tmp_path: Path) -> None:
    coordinator, alias_hash = _coordinator(tmp_path)
    receipt = tmp_path / "leases" / f"{alias_hash}.receipt.json"
    receipt.write_text("{not json", encoding="utf-8")
    with pytest.raises(AgyAccountPoolBusyError):
        coordinator.acquire_claim("desktop-new", wait_timeout=0)
    assert receipt.read_text(encoding="utf-8") == "{not json"


def test_held_lock_with_dead_owner_is_not_reclaimed(tmp_path: Path) -> None:
    """A provider that inherited the lock keeps the account busy after its dispatcher died."""
    coordinator, alias_hash = _coordinator(tmp_path)
    receipt = _write_receipt(tmp_path, alias_hash)
    holder = (tmp_path / "leases" / f"{alias_hash}.lock").open("a+")
    fcntl.flock(holder.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        with pytest.raises(AgyAccountPoolBusyError):
            coordinator.acquire_claim("desktop-new", wait_timeout=0)
        assert receipt.exists()
    finally:
        holder.close()


def test_inherited_lock_in_surviving_child_blocks_reclaim_until_it_exits(tmp_path: Path) -> None:
    """Real fd inheritance: a provider holding the passed lease fd outlives its dispatcher."""
    coordinator, alias_hash = _coordinator(tmp_path)
    claim = coordinator.acquire_claim("desktop-dying", wait_timeout=0)
    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        pass_fds=(claim.lock_file_obj.fileno(),),
        start_new_session=True,
    )
    try:
        # The dispatcher "dies": its own descriptor closes without LOCK_UN and
        # the receipt survives with a dead owner PID.
        claim.lock_file_obj.close()
        claim.released = True
        receipt = claim.receipt_path
        data = json.loads(receipt.read_text(encoding="utf-8"))
        data["pid"] = _dead_pid()
        receipt.write_text(json.dumps(data) + "\n", encoding="utf-8")
        with pytest.raises(AgyAccountPoolBusyError):
            coordinator.acquire_claim("desktop-new", wait_timeout=0)
        assert receipt.exists()
    finally:
        child.kill()
        child.wait()
    reclaimed = coordinator.acquire_claim("desktop-new", wait_timeout=0)
    try:
        assert reclaimed.account_alias_hash == alias_hash
    finally:
        reclaimed.release()


def test_run_agy_never_passes_stdio_fds(monkeypatch, tmp_path: Path) -> None:
    captured: dict = {}

    class _Stop(Exception):
        pass

    def fake_popen(*args, **kwargs):
        captured.update(kwargs)
        raise _Stop()

    monkeypatch.setattr(dispatch.shutil, "which", lambda _name: "/bin/true")
    monkeypatch.setattr(dispatch.subprocess, "Popen", fake_popen)
    with pytest.raises(_Stop):
        dispatch.run_agy(
            env=dict(os.environ),
            prompt="p",
            cwd=str(tmp_path),
            mode="plan",
            model=GEMINI,
            effort=None,
            timeout=5,
            lease_fd=2,
        )
    assert captured["pass_fds"] == ()


# --- dispatcher -----------------------------------------------------------


@pytest.fixture
def pool(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("NEXUS_AGY_MODEL_CATALOG_CHECK", "0")
    monkeypatch.setenv("NEXUS_AGY_POOL_QUEUE_POLL_SECONDS", "0.1")
    for name in (
        "NEXUS_AGY_POOL_WAIT_TIMEOUT",
        "NEXUS_AGY_PREFERRED_ACCOUNTS",
        "NEXUS_AGY_RESERVE_ACCOUNTS",
        "NEXUS_AGY_FALLBACK_ACCOUNTS",
        "NEXUS_AGY_BLOCKED_ACCOUNTS",
    ):
        monkeypatch.delenv(name, raising=False)
    metas: list[dict] = []
    monkeypatch.setattr(dispatch, "emit_meta", lambda meta: metas.append(dict(meta)))
    home = tmp_path / "home-a"
    home.mkdir()
    checked_at = "2099-01-01T00:00:00+00:00"
    snapshot = {
        "checked_at": checked_at,
        "accounts": [
            {
                "account": "a",
                "checked_at": checked_at,
                "ok": True,
                "groups": {
                    "Gemini Models": {
                        "5h": {"status": "known", "remaining_pct": 100.0, "reset_at": None}
                    }
                },
            }
        ],
    }
    state = {
        "family": "gemini",
        "snapshot_fresh": True,
        "preferred": [],
        "reserve": [],
        "fallback": [],
        "blocked": [],
        "unknown": [],
    }
    monkeypatch.setattr(dispatch, "_apply_dynamic_availability", lambda _m: (snapshot, state))
    coordinator = CrossProcessLeaseCoordinator(
        manager=AgyAccountPoolManager(
            accounts=[AgyAccount(alias="a", home_dir=str(home))], use_real_manager=False
        ),
        allocator_lock_path=tmp_path / "allocator.lock",
        leases_dir=tmp_path / "leases",
        poll_interval=0.02,
    )
    return SimpleNamespace(coordinator=coordinator, leases=tmp_path / "leases", metas=metas)


def _dispatch_kwargs(pool, runner) -> dict:
    return dict(
        prompt="work",
        cwd=str(ROOT),
        mode="plan",
        model=GEMINI,
        timeout=60,
        max_calls=1,
        coordinator=pool.coordinator,
        run_agy_fn=runner,
    )


def test_dispatcher_hands_the_lease_lock_to_the_runner(pool) -> None:
    seen: dict = {}

    def runner(*, env, prompt, cwd, mode, model, effort, timeout, lease_fd=None):
        seen["lease_fd"] = lease_fd
        lock_files = list(pool.leases.glob("*.lock"))
        assert len(lock_files) == 1
        seen["same_inode"] = os.fstat(lease_fd).st_ino == lock_files[0].stat().st_ino
        return 0, "done", "", False, 10

    assert dispatch.dispatch_run(**_dispatch_kwargs(pool, runner)) == 0
    assert isinstance(seen["lease_fd"], int) and seen["same_inode"]
    assert not list(pool.leases.glob("*.receipt.json"))


def test_run_agy_passes_lease_fd_to_provider(monkeypatch, tmp_path: Path) -> None:
    captured: dict = {}

    class _Stop(Exception):
        pass

    def fake_popen(*args, **kwargs):
        captured.update(kwargs)
        raise _Stop()

    monkeypatch.setattr(dispatch.shutil, "which", lambda _name: "/bin/true")
    monkeypatch.setattr(dispatch.subprocess, "Popen", fake_popen)
    with (tmp_path / "x.lock").open("a+") as lock_obj:
        with pytest.raises(_Stop):
            dispatch.run_agy(
                env=dict(os.environ),
                prompt="p",
                cwd=str(tmp_path),
                mode="plan",
                model=GEMINI,
                effort=None,
                timeout=5,
                lease_fd=lock_obj.fileno(),
            )
        assert captured["pass_fds"] == (lock_obj.fileno(),)
        assert captured["start_new_session"] is True


@pytest.mark.skipif(threading.current_thread() is not threading.main_thread(), reason="signals")
def test_sigterm_on_foreground_dispatch_releases_receipt(pool) -> None:
    prior = signal.getsignal(signal.SIGTERM)

    def runner(*, env, prompt, cwd, mode, model, effort, timeout):
        assert list(pool.leases.glob("*.receipt.json"))
        os.kill(os.getpid(), signal.SIGTERM)
        threading.Event().wait(5)
        raise AssertionError("SIGTERM was not delivered")

    code = dispatch._run_foreground_with_signal_cleanup(
        dispatch.dispatch_run, **_dispatch_kwargs(pool, runner)
    )
    assert code == 128 + signal.SIGTERM
    assert not list(pool.leases.glob("*.receipt.json"))
    assert signal.getsignal(signal.SIGTERM) is prior
    assert any(meta.get("failure_kind") == "FOREGROUND_SIGNAL:SIGTERM" for meta in pool.metas)
    # The account is immediately claimable again.
    pool.coordinator.acquire_claim("desktop-next", wait_timeout=0).release()
