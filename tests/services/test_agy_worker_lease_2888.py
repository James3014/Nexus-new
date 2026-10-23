"""#2888: ``--run-as-user`` keeps the account fail-closed while a worker agy may still run.

* ``AccountLeaseClaim.mark_worker_run`` records the worker run in the durable
  lease receipt, atomically, before anything launches.
* The pool's orphaned-receipt reclaim keeps a receipt with ``worker_*`` fields
  unless ``reap_orphaned_worker_run`` proves the run is gone (sudo closes the
  inherited lease fd, so a free lock plus a dead dispatcher proves nothing).
* The dispatcher marks before launch, fails closed when it cannot mark, and
  never releases the claim after an unclean worker sweep.
* The default (Owner-uid) agy profile denies the worker-runs tree; the
  ``--run-as-user`` profile is unchanged.
"""

from __future__ import annotations

import ast
import fcntl
import functools
import grp
import json
import logging
import os
import pwd
import re
import shutil
import subprocess
import sys
import tempfile
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from nexus.executors import agy_dispatch_boundary as boundary_mod
from nexus.executors import agy_worker_account as worker_mod
from nexus.executors import agy_write_admission as admission
from nexus.executors import cli_worker
from nexus.services import agy_account_pool as agy_pool
from nexus.services.agy_account_pool import (
    AccountLeaseClaim,
    AgyAccount,
    AgyAccountPoolBusyError,
    AgyAccountPoolError,
    AgyAccountPoolManager,
    CrossProcessLeaseCoordinator,
    _reclaim_orphaned_desktop_receipt,
)

ROOT = Path(__file__).resolve().parents[2]
DISPATCH_PATH = ROOT / "scripts" / "ops" / "nexus-agy-dispatch"
WRAPPER = ROOT / "scripts" / "ops" / "agy-worker-exec"
os.environ["NEXUS_AGY_SNAPSHOT"] = str(ROOT)
dispatch = SourceFileLoader(
    "nexus_agy_dispatch_worker_lease_2888", str(DISPATCH_PATH)
).load_module()

TOKEN = Path(".gemini") / "antigravity-cli" / "antigravity-oauth-token"
INSTALLATION_ID = Path(".gemini") / "antigravity-cli" / "installation_id"
RUN_TAG = "ab" * 16
SWEEP_CLEAN = "AGY_WORKER_SWEEP clean\n"
SWEEP_UNCLEAN = "AGY_WORKER_SWEEP unclean 4242\n"

# Real ``ps`` / ``sandbox-exec`` probes only exist as test nodes on macOS (same
# convention as the #2795 Seatbelt witness file): a Linux skip would be an added
# test id that never passes, which the impact gate rightly refuses.
DARWIN_WITNESS_AVAILABLE = sys.platform == "darwin" and os.path.exists(admission.SANDBOX_EXEC_PATH)
DARWIN_WITNESSES = (
    "test_real_ps_unknown_user_and_busy_user_are_never_read_as_empty",
    "test_real_ps_user_without_processes_is_empty",
    "test_default_profile_blocks_a_real_listing_of_a_worker_runs_dir",
    "test_default_profile_denies_real_writes_and_reads_under_worker_runs",
)


def darwin_witness(func, *, available: bool = DARWIN_WITNESS_AVAILABLE):
    """Expose a macOS witness as a test node only where it can run."""
    return func if available else None


def test_darwin_witness_nodes_are_declared_and_darwin_ci_must_collect_them() -> None:
    """Always collected (Linux included), so the impact gate sees a passing node."""
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    declared = {
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and any(isinstance(d, ast.Name) and d.id == "darwin_witness" for d in node.decorator_list)
    }
    assert declared == set(DARWIN_WITNESSES)
    for name in DARWIN_WITNESSES:
        assert (globals().get(name) is not None) is DARWIN_WITNESS_AVAILABLE
    if os.environ.get("CI") and sys.platform == "darwin":
        assert DARWIN_WITNESS_AVAILABLE, "macOS CI host has no sandbox-exec"


@pytest.fixture(autouse=True)
def _fresh_worker_reap_cache():
    """The pool keeps a process-local negative cache of unproven worker receipts."""
    agy_pool._WORKER_REAP_UNPROVEN.clear()
    yield
    agy_pool._WORKER_REAP_UNPROVEN.clear()


@pytest.fixture
def reap_clock(monkeypatch):
    """A controllable clock for the pool's 60 s negative cache."""
    clock = SimpleNamespace(now=1000.0)
    monkeypatch.setattr(agy_pool, "_reap_monotonic", lambda: clock.now)
    return clock


# ---------------------------------------------------------------------------
# pool: mark_worker_run
# ---------------------------------------------------------------------------


def _dead_pid() -> int:
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    return proc.pid


def _coordinator(
    tmp_path: Path, aliases: tuple[str, ...] = ("a",), poll_interval: float | None = None
) -> tuple[CrossProcessLeaseCoordinator, str]:
    accounts = []
    for alias in aliases:
        home = tmp_path / f"home-{alias}"
        home.mkdir(exist_ok=True)
        accounts.append(AgyAccount(alias=alias, home_dir=str(home)))
    manager = AgyAccountPoolManager(accounts=accounts, use_real_manager=False)
    extra = {} if poll_interval is None else {"poll_interval": poll_interval}
    coordinator = CrossProcessLeaseCoordinator(
        manager=manager,
        allocator_lock_path=tmp_path / "allocator.lock",
        leases_dir=tmp_path / "leases",
        default_wait_timeout=0,
        **extra,
    )
    (tmp_path / "leases").mkdir(exist_ok=True)
    return coordinator, manager._accounts[0].alias_hash


def _worker_fields(run_root: str = f"/runs/{RUN_TAG}") -> dict[str, Any]:
    return {
        "worker_run_root": run_root,
        "worker_run_root_id": [16777231, 4242],
        "worker_run_as_user": worker_mod.WORKER_USER,
    }


def _write_receipt(tmp_path: Path, alias_hash: str, **fields: Any) -> Path:
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


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _mark(claim: AccountLeaseClaim, **overrides: Any) -> None:
    kwargs: dict[str, Any] = {
        "run_root": f"/runs/{RUN_TAG}",
        "run_root_id": [16777231, 4242],
        "run_as_user": worker_mod.WORKER_USER,
    }
    kwargs.update(overrides)
    claim.mark_worker_run(**kwargs)


def test_mark_worker_run_adds_the_three_fields_and_keeps_the_rest(tmp_path: Path) -> None:
    coordinator, _alias = _coordinator(tmp_path)
    claim = coordinator.acquire_claim("desktop-mark", wait_timeout=0)
    try:
        before = _read(claim.receipt_path)
        mode_before = claim.receipt_path.stat().st_mode
        _mark(claim)
        after = _read(claim.receipt_path)
        assert after == {**before, **_worker_fields()}
        assert claim.receipt_path.stat().st_mode == mode_before
        # no temp file is left behind in the leases dir
        assert sorted(p.name for p in claim.receipt_path.parent.iterdir() if ".tmp" in p.name) == []
        # the claim is still fully usable: release removes the marked receipt
    finally:
        claim.release()
    assert not claim.receipt_path.exists()


def test_mark_worker_run_is_an_atomic_same_directory_replace(tmp_path: Path, monkeypatch) -> None:
    coordinator, _alias = _coordinator(tmp_path)
    claim = coordinator.acquire_claim("desktop-mark", wait_timeout=0)
    replaced: list[tuple[Path, Path]] = []
    synced: list[int] = []
    real_replace, real_fsync = os.replace, os.fsync

    def spy_replace(src, dst, *a, **k):
        # the new content is complete on disk before it becomes visible
        replaced.append((Path(src), Path(dst)))
        assert _read(Path(src))["worker_run_root"] == f"/runs/{RUN_TAG}"
        assert _read(Path(dst)).get("worker_run_root") is None
        return real_replace(src, dst, *a, **k)

    def spy_fsync(fd):
        synced.append(fd)
        return real_fsync(fd)

    monkeypatch.setattr(os, "replace", spy_replace)
    monkeypatch.setattr(os, "fsync", spy_fsync)
    try:
        _mark(claim)
    finally:
        claim.release()
    assert len(replaced) == 1 and synced
    src, dst = replaced[0]
    assert dst == claim.receipt_path and src.parent == dst.parent and src != dst


def test_mark_worker_run_failure_keeps_the_old_receipt_and_cleans_the_temp(
    tmp_path: Path, monkeypatch
) -> None:
    coordinator, _alias = _coordinator(tmp_path)
    claim = coordinator.acquire_claim("desktop-mark", wait_timeout=0)
    try:
        before = claim.receipt_path.read_text(encoding="utf-8")

        def boom(*_a, **_k):
            raise OSError(28, "No space left on device")

        monkeypatch.setattr(os, "replace", boom)
        with pytest.raises(AgyAccountPoolError, match="AGY_WORKER_LEASE_MARK_FAILED:OSError"):
            _mark(claim)
        assert claim.receipt_path.read_text(encoding="utf-8") == before
        assert [p.name for p in claim.receipt_path.parent.iterdir() if ".tmp" in p.name] == []
        monkeypatch.undo()
        _mark(claim)  # a later attempt still works
        assert _read(claim.receipt_path)["worker_run_as_user"] == worker_mod.WORKER_USER
    finally:
        claim.release()


@pytest.mark.parametrize(
    "tamper",
    [
        pytest.param({"account_alias_hash": "000000000000"}, id="account-mismatch"),
        pytest.param({"lease_id_hash": "000000000000"}, id="lease-mismatch"),
        pytest.param({"pid": 1}, id="pid-mismatch"),
        pytest.param({"pid": "not-an-int"}, id="pid-not-int"),
        pytest.param({"pid": True}, id="pid-bool"),
    ],
)
def test_mark_worker_run_refuses_a_receipt_that_is_not_this_claims(
    tmp_path: Path, tamper: dict[str, Any]
) -> None:
    coordinator, _alias = _coordinator(tmp_path)
    claim = coordinator.acquire_claim("desktop-mark", wait_timeout=0)
    try:
        data = _read(claim.receipt_path)
        data.update(tamper)
        claim.receipt_path.write_text(json.dumps(data) + "\n", encoding="utf-8")
        before = claim.receipt_path.read_text(encoding="utf-8")
        with pytest.raises(AgyAccountPoolError, match="AGY_WORKER_LEASE_MARK_REFUSED"):
            _mark(claim)
        assert claim.receipt_path.read_text(encoding="utf-8") == before
    finally:
        claim.release()


@pytest.mark.parametrize("content", [None, "{not json", "[]"], ids=["missing", "garbled", "list"])
def test_mark_worker_run_refuses_a_missing_or_unreadable_receipt(
    tmp_path: Path, content: str | None
) -> None:
    coordinator, _alias = _coordinator(tmp_path)
    claim = coordinator.acquire_claim("desktop-mark", wait_timeout=0)
    try:
        if content is None:
            claim.receipt_path.unlink()
        else:
            claim.receipt_path.write_text(content, encoding="utf-8")
        with pytest.raises(AgyAccountPoolError, match="AGY_WORKER_LEASE_MARK_REFUSED"):
            _mark(claim)
        assert claim.receipt_path.exists() is (content is not None)
    finally:
        claim.release()


def test_mark_worker_run_refuses_after_release(tmp_path: Path) -> None:
    coordinator, _alias = _coordinator(tmp_path)
    claim = coordinator.acquire_claim("desktop-mark", wait_timeout=0)
    claim.release()
    with pytest.raises(AgyAccountPoolError, match="claim_released"):
        _mark(claim)
    assert not claim.receipt_path.exists()  # nothing was resurrected


# ---------------------------------------------------------------------------
# pool: reclaim of orphaned receipts
# ---------------------------------------------------------------------------


@pytest.fixture
def reaper(monkeypatch):
    """Replace the worker module's reaper; records every receipt it is shown."""
    state = SimpleNamespace(calls=[], result=True)

    def fake(receipt, **_kwargs):
        state.calls.append(dict(receipt))
        if isinstance(state.result, BaseException):
            raise state.result
        return state.result

    monkeypatch.setattr(worker_mod, "reap_orphaned_worker_run", fake)
    return state


def test_receipt_without_worker_fields_is_reclaimed_without_asking_the_reaper(
    tmp_path: Path, reaper
) -> None:
    coordinator, alias_hash = _coordinator(tmp_path)
    old = _write_receipt(tmp_path, alias_hash)
    claim = coordinator.acquire_claim("desktop-new", wait_timeout=0)
    try:
        assert claim.account_alias_hash == alias_hash
        assert _read(old)["consumer_id"] == "desktop-new"
    finally:
        claim.release()
    assert reaper.calls == []


@pytest.mark.parametrize(
    "result",
    [False, None, "yes", 1, RuntimeError("boom"), OSError("boom")],
    ids=["false", "none", "truthy-str", "truthy-int", "runtime-error", "os-error"],
)
def test_worker_receipt_is_preserved_unless_the_reaper_returns_true(
    tmp_path: Path, reaper, caplog, result: Any
) -> None:
    coordinator, alias_hash = _coordinator(tmp_path)
    receipt = _write_receipt(tmp_path, alias_hash, **_worker_fields())
    before = receipt.read_text(encoding="utf-8")
    reaper.result = result
    with caplog.at_level(logging.WARNING, logger="nexus.services.agy_account_pool"):
        with pytest.raises(AgyAccountPoolBusyError):
            coordinator.acquire_claim("desktop-new", wait_timeout=0)
    assert receipt.read_text(encoding="utf-8") == before
    assert len(reaper.calls) == 1 and reaper.calls[0]["worker_run_as_user"]
    assert (
        f"AGY_ORPHANED_WORKER_RECEIPT_PRESERVED account={alias_hash} lease=deadbeef0001"
        in caplog.text
    )


def test_worker_receipt_is_removed_when_the_reaper_proves_the_run_gone(
    tmp_path: Path, reaper, caplog
) -> None:
    coordinator, alias_hash = _coordinator(tmp_path)
    old = _write_receipt(tmp_path, alias_hash, **_worker_fields())
    reaper.result = True
    with caplog.at_level(logging.WARNING, logger="nexus.services.agy_account_pool"):
        claim = coordinator.acquire_claim("desktop-new", wait_timeout=0)
    try:
        assert claim.account_alias_hash == alias_hash
        new = _read(old)
        assert new["consumer_id"] == "desktop-new" and "worker_run_root" not in new
    finally:
        claim.release()
    assert "AGY_ORPHANED_DESKTOP_RECEIPT_RECLAIMED" in caplog.text
    assert "AGY_ORPHANED_WORKER_RECEIPT_PRESERVED" not in caplog.text


@pytest.mark.parametrize(
    "fields",
    [
        pytest.param({"pid": os.getppid()}, id="live-pid"),
        pytest.param({"consumer_id": "model-probe:task-1"}, id="non-desktop-consumer"),
        pytest.param({"account_alias_hash": "000000000000"}, id="identity-mismatch"),
    ],
)
def test_the_existing_reclaim_checks_still_run_before_the_reaper(
    tmp_path: Path, reaper, fields: dict[str, Any]
) -> None:
    coordinator, alias_hash = _coordinator(tmp_path)
    receipt = _write_receipt(tmp_path, alias_hash, **_worker_fields(), **fields)
    deferred: list = []
    assert _reclaim_orphaned_desktop_receipt(receipt, alias_hash, defer=deferred) is False
    assert receipt.exists() and reaper.calls == [] and deferred == []


def test_any_worker_prefixed_key_is_deferred_and_never_reaped_inline(
    tmp_path: Path, reaper
) -> None:
    coordinator, alias_hash = _coordinator(tmp_path)
    receipt = _write_receipt(tmp_path, alias_hash, worker_future_field=1)
    deferred: list = []
    assert _reclaim_orphaned_desktop_receipt(receipt, alias_hash, defer=deferred) is False
    assert deferred == [(alias_hash, receipt, "deadbeef0001")]
    # without a defer list the answer is the same and nothing is removed
    assert _reclaim_orphaned_desktop_receipt(receipt, alias_hash) is False
    assert receipt.exists() and reaper.calls == []


# ---------------------------------------------------------------------------
# worker module: reap_orphaned_worker_run
# ---------------------------------------------------------------------------


class _Commands:
    """A fake ``run_command`` that answers sudo-sweep and ps calls and records them."""

    def __init__(
        self,
        *,
        sweep: tuple[int, str] | BaseException = (0, SWEEP_CLEAN),
        ps: tuple[int, str, str] | BaseException = (1, "", ""),
    ) -> None:
        self.sweep, self.ps = sweep, ps
        self.calls: list[tuple[list[str], dict[str, Any]]] = []

    def __call__(self, argv, **kwargs):
        self.calls.append((list(argv), kwargs))
        answer = self.ps if argv[0] == worker_mod.PS_PATH else self.sweep
        if isinstance(answer, BaseException):
            raise answer
        if argv[0] == worker_mod.PS_PATH:
            code, out, err = answer
        else:
            (code, out), err = answer, ""
        return subprocess.CompletedProcess(argv, code, out, err)

    @property
    def sweeps(self) -> list[list[str]]:
        return [argv for argv, _ in self.calls if argv[0] == worker_mod.SUDO_PATH]

    @property
    def pses(self) -> list[tuple[list[str], dict[str, Any]]]:
        return [call for call in self.calls if call[0][0] == worker_mod.PS_PATH]


@pytest.fixture
def runs(tmp_path: Path, monkeypatch) -> Path:
    base = tmp_path.resolve()
    runs_dir = base / "worker-runs"
    runs_dir.mkdir()
    monkeypatch.setattr(worker_mod, "WORKER_RUNS", runs_dir)
    return runs_dir


def _run_root(runs_dir: Path, tag: str = RUN_TAG) -> tuple[Path, dict[str, Any]]:
    root = runs_dir / tag
    root.mkdir()
    (root / "work").mkdir()
    (root / "work" / "a.py").write_text("x\n", encoding="utf-8")
    info = os.lstat(root)
    receipt = {
        "worker_run_root": str(root),
        "worker_run_root_id": [info.st_dev, info.st_ino],
        "worker_run_as_user": worker_mod.WORKER_USER,
    }
    return root, receipt


def test_existing_root_with_a_clean_sweep_is_removed_and_proven(runs: Path) -> None:
    root, receipt = _run_root(runs)
    commands = _Commands()
    assert worker_mod.reap_orphaned_worker_run(receipt, run_command=commands) is True
    assert not os.path.lexists(root)
    assert commands.sweeps == [worker_mod.sweep_argv(root, [])]
    assert commands.pses == []  # the sweep's own verdict is the evidence here


@pytest.mark.parametrize(
    "sweep",
    [
        pytest.param((3, SWEEP_UNCLEAN), id="unclean"),
        pytest.param((1, ""), id="sudo-refused"),
        pytest.param((0, "garbage\n"), id="no-clean-line"),
        pytest.param(OSError("sudo missing"), id="oserror"),
        pytest.param(subprocess.TimeoutExpired(["sudo"], 30), id="timeout"),
    ],
)
def test_existing_root_without_a_clean_sweep_is_kept(runs: Path, sweep: Any) -> None:
    root, receipt = _run_root(runs)
    commands = _Commands(sweep=sweep)
    assert worker_mod.reap_orphaned_worker_run(receipt, run_command=commands) is False
    assert (root / "work" / "a.py").read_text(encoding="utf-8") == "x\n"
    assert len(commands.sweeps) == 1


def test_a_clean_sweep_proves_the_run_gone_even_if_leftovers_remain(
    runs: Path, monkeypatch, caplog
) -> None:
    root, receipt = _run_root(runs)
    monkeypatch.setattr(worker_mod.shutil, "rmtree", lambda *a, **k: None)
    with caplog.at_level(logging.WARNING, logger=worker_mod.__name__):
        assert worker_mod.reap_orphaned_worker_run(receipt, run_command=_Commands()) is True
    assert root.exists()  # best-effort removal: the tree stays, the proof does not depend on it
    assert str(root) in caplog.text and "LEFTOVER" in caplog.text


def _not_the_recorded_directory(case: str, runs_dir: Path, monkeypatch) -> tuple[Path, dict]:
    """A run root that exists but is not the directory the receipt recorded."""
    if case == "file":
        root = runs_dir / RUN_TAG
        root.write_text("file", encoding="utf-8")
        info = os.lstat(root)
        return root, {
            "worker_run_root": str(root),
            "worker_run_root_id": [info.st_dev, info.st_ino],
            "worker_run_as_user": worker_mod.WORKER_USER,
        }
    root, receipt = _run_root(runs_dir)
    if case == "other-inode":
        # e.g. after a reboot; inode numbers are reused on some filesystems, so the
        # receipt is altered instead of recreating the directory
        dev, ino = receipt["worker_run_root_id"]
        receipt["worker_run_root_id"] = [dev, ino + 1]
    elif case == "other-device":
        dev, ino = receipt["worker_run_root_id"]
        receipt["worker_run_root_id"] = [dev + 1, ino]
    elif case == "other-owner":
        monkeypatch.setattr(worker_mod.os, "getuid", lambda: os.lstat(root).st_uid + 1)
    else:  # pragma: no cover
        raise AssertionError(case)
    return root, receipt


@pytest.mark.parametrize("case", ["file", "other-inode", "other-device", "other-owner"])
@pytest.mark.parametrize(
    ("ps", "proven"),
    [((1, "", ""), True), ((0, "  4242\n", ""), False), ((2, "", ""), False)],
    ids=["no-worker-process", "worker-process-alive", "ps-error"],
)
def test_a_root_that_is_not_the_recorded_directory_falls_back_to_the_ps_proof(
    runs: Path, monkeypatch, case: str, ps: tuple, proven: bool
) -> None:
    root, receipt = _not_the_recorded_directory(case, runs, monkeypatch)
    commands = _Commands(ps=ps)
    assert worker_mod.reap_orphaned_worker_run(receipt, run_command=commands) is proven
    assert root.exists()  # never swept, never removed
    assert commands.sweeps == [] and len(commands.pses) == 1


def test_a_dangling_symlink_root_is_refused(runs: Path, tmp_path: Path) -> None:
    root = runs / RUN_TAG
    root.symlink_to(tmp_path / "nowhere")
    receipt = {
        "worker_run_root": str(root),
        "worker_run_root_id": [1, 2],
        "worker_run_as_user": worker_mod.WORKER_USER,
    }
    commands = _Commands()
    assert worker_mod.reap_orphaned_worker_run(receipt, run_command=commands) is False
    assert commands.calls == []


def _invalid_receipts(runs_dir: Path) -> list[Any]:
    root = runs_dir / RUN_TAG
    good: dict[str, Any] = {
        "worker_run_root": str(root),
        "worker_run_root_id": [3, 4],
        "worker_run_as_user": worker_mod.WORKER_USER,
    }

    def bad(**fields: Any) -> dict[str, Any]:
        return {**good, **fields}

    outside = runs_dir.parent / "elsewhere"
    return [
        pytest.param(bad(worker_run_as_user="root"), id="user-root"),
        pytest.param(bad(worker_run_as_user=None), id="user-none"),
        pytest.param(
            {k: v for k, v in good.items() if k != "worker_run_as_user"}, id="user-absent"
        ),
        pytest.param(bad(worker_run_root=None), id="root-none"),
        pytest.param(bad(worker_run_root=123), id="root-int"),
        pytest.param(bad(worker_run_root=""), id="root-empty"),
        pytest.param(bad(worker_run_root=str(root) + "\x00x"), id="root-nul"),
        pytest.param(bad(worker_run_root=RUN_TAG), id="root-relative"),
        pytest.param(bad(worker_run_root=str(root) + "/"), id="root-trailing-slash"),
        pytest.param(bad(worker_run_root=f"{runs_dir}/x/../{RUN_TAG}"), id="root-dotdot"),
        pytest.param(bad(worker_run_root=str(outside / RUN_TAG)), id="root-outside-runs"),
        pytest.param(bad(worker_run_root=str(runs_dir / "sub" / RUN_TAG)), id="root-nested"),
        pytest.param(bad(worker_run_root=str(runs_dir)), id="root-is-runs-dir"),
        pytest.param(bad(worker_run_root=str(runs_dir / RUN_TAG.upper())), id="name-uppercase"),
        pytest.param(bad(worker_run_root=str(runs_dir / RUN_TAG[:-1])), id="name-31-chars"),
        pytest.param(bad(worker_run_root=str(runs_dir / (RUN_TAG + "a"))), id="name-33-chars"),
        pytest.param(bad(worker_run_root=str(runs_dir / ("g" * 32))), id="name-not-hex"),
        pytest.param(bad(worker_run_root_id=None), id="id-none"),
        pytest.param(bad(worker_run_root_id=[1]), id="id-short"),
        pytest.param(bad(worker_run_root_id=[1, 2, 3]), id="id-long"),
        pytest.param(bad(worker_run_root_id=[True, 2]), id="id-bool"),
        pytest.param(bad(worker_run_root_id=["1", 2]), id="id-str"),
        pytest.param(bad(worker_run_root_id=[1.0, 2]), id="id-float"),
        pytest.param(bad(worker_run_root_id=(1, 2)), id="id-tuple"),
        pytest.param(bad(worker_run_root_id="12"), id="id-string"),
        pytest.param(None, id="receipt-none"),
        pytest.param({}, id="receipt-empty"),
    ]


def test_reaper_input_validation(runs: Path) -> None:
    ids = {param.id: param.values[0] for param in _invalid_receipts(runs)}
    assert len(ids) == len(_invalid_receipts(runs))
    for name, receipt in ids.items():
        commands = _Commands()
        assert worker_mod.reap_orphaned_worker_run(receipt, run_command=commands) is False, name
        assert commands.calls == [], name  # nothing is signalled or listed on bad input


def test_reaper_rejects_a_symlinked_run_root_and_leaves_its_target_alone(
    runs: Path, tmp_path: Path
) -> None:
    victim = tmp_path / "victim"
    (victim / "keep").mkdir(parents=True)
    root = runs / RUN_TAG
    root.symlink_to(victim)
    info = os.lstat(victim)
    receipt = {
        "worker_run_root": str(root),
        "worker_run_root_id": [info.st_dev, info.st_ino],
        "worker_run_as_user": worker_mod.WORKER_USER,
    }
    commands = _Commands()
    assert worker_mod.reap_orphaned_worker_run(receipt, run_command=commands) is False
    assert (victim / "keep").is_dir() and commands.calls == []


def test_reaper_uses_the_runs_dir_current_value_not_a_stale_default(
    runs: Path, tmp_path: Path, monkeypatch
) -> None:
    root, receipt = _run_root(runs)
    other = tmp_path.resolve() / "other-runs"
    other.mkdir()
    monkeypatch.setattr(worker_mod, "WORKER_RUNS", other)
    commands = _Commands()
    assert worker_mod.reap_orphaned_worker_run(receipt, run_command=commands) is False
    assert root.exists() and commands.calls == []


def _missing_root_receipt(runs_dir: Path) -> dict[str, Any]:
    return {
        "worker_run_root": str(runs_dir / RUN_TAG),
        "worker_run_root_id": [3, 4],
        "worker_run_as_user": worker_mod.WORKER_USER,
    }


def test_missing_root_is_proven_only_when_the_worker_account_owns_no_process(runs: Path) -> None:
    commands = _Commands(ps=(1, "", ""))
    assert worker_mod.reap_orphaned_worker_run(_missing_root_receipt(runs), run_command=commands)
    assert commands.sweeps == []  # the wrapper refuses a missing root
    ((argv, kwargs),) = commands.pses
    assert argv == ["/bin/ps", "-U", worker_mod.WORKER_USER, "-o", "pid="]
    assert kwargs["timeout"] == 10 and kwargs["capture_output"] is True
    assert kwargs["env"] == {"PATH": "/usr/bin:/bin", "LC_ALL": "C"}


@pytest.mark.parametrize(
    "ps",
    [
        pytest.param((0, "  4242\n", ""), id="one-pid"),
        pytest.param((0, "  4242\n  4343\n", ""), id="two-pids"),
        pytest.param((1, "  4242\n", ""), id="pid-with-no-match-code"),
        pytest.param((0, "", ""), id="success-but-empty"),
        pytest.param((1, "", "ps: No ruser named '_cairnwork_worker'\n"), id="unknown-user"),
        pytest.param((1, "", "ps: something odd\n"), id="stderr-noise"),
        pytest.param((2, "", ""), id="unknown-exit-code"),
        pytest.param((-9, "", ""), id="killed"),
        pytest.param(OSError("no ps"), id="oserror"),
        pytest.param(subprocess.TimeoutExpired(["ps"], 10), id="timeout"),
        pytest.param(ValueError("weird"), id="unexpected-exception"),
    ],
)
def test_missing_root_with_any_sign_of_a_worker_process_or_error_is_unproven(
    runs: Path, ps: Any
) -> None:
    commands = _Commands(ps=ps)
    assert not worker_mod.reap_orphaned_worker_run(
        _missing_root_receipt(runs), run_command=commands
    )


@darwin_witness  # ps -U exit codes observed on macOS 27
def test_real_ps_unknown_user_and_busy_user_are_never_read_as_empty() -> None:
    # An unknown user exits 1 with empty stdout like "no process" but names the user on stderr.
    assert worker_mod._worker_user_has_no_process("nosuchuser_zz_2888", subprocess.run) is False
    # The current user owns at least this pytest process.
    me = pwd.getpwuid(os.getuid()).pw_name
    assert worker_mod._worker_user_has_no_process(me, subprocess.run) is False


@darwin_witness  # ps -U exit codes observed on macOS 27
def test_real_ps_user_without_processes_is_empty() -> None:
    # Also holds where the worker account is not installed: ps then names it on stderr.
    listing = subprocess.run(
        ["/bin/ps", "-U", worker_mod.WORKER_USER, "-o", "pid="],
        capture_output=True,
        text=True,
        check=False,
    )
    expected = listing.returncode == 1 and not listing.stdout.strip() and not listing.stderr.strip()
    # whatever the account is doing right now, the helper agrees with a direct ps
    assert (
        worker_mod._worker_user_has_no_process(worker_mod.WORKER_USER, subprocess.run) is expected
    )


def test_reaper_never_raises(runs: Path, monkeypatch) -> None:
    root, receipt = _run_root(runs)

    def boom(*_a, **_k):
        raise RuntimeError("boom")

    monkeypatch.setattr(worker_mod, "sweep_run_root", boom)
    assert worker_mod.reap_orphaned_worker_run(receipt, run_command=_Commands()) is False
    assert root.exists()
    monkeypatch.setattr(worker_mod.os.path, "lexists", boom)
    assert worker_mod.reap_orphaned_worker_run(receipt, run_command=_Commands()) is False


def test_reaper_end_to_end_through_the_pool(
    tmp_path: Path, runs: Path, monkeypatch, reap_clock
) -> None:
    """A real receipt, the real reclaim path and the real reaper (fake sudo and ps)."""
    coordinator, alias_hash = _coordinator(tmp_path)
    root, worker_fields = _run_root(runs)
    commands = _Commands()
    real_reaper = worker_mod.reap_orphaned_worker_run
    monkeypatch.setattr(
        worker_mod,
        "reap_orphaned_worker_run",
        lambda receipt: real_reaper(receipt, run_command=commands),
    )
    receipt = _write_receipt(tmp_path, alias_hash, **worker_fields)

    commands.sweep = (3, SWEEP_UNCLEAN)
    with pytest.raises(AgyAccountPoolBusyError):
        coordinator.acquire_claim("desktop-new", wait_timeout=0)
    assert receipt.exists() and root.exists()

    commands.sweep = (0, SWEEP_CLEAN)
    reap_clock.now += agy_pool.WORKER_REAP_NEGATIVE_TTL_SECONDS + 1  # the unproven verdict expired
    claim = coordinator.acquire_claim("desktop-new", wait_timeout=0)
    try:
        assert not root.exists() and _read(receipt)["consumer_id"] == "desktop-new"
    finally:
        claim.release()


# ---------------------------------------------------------------------------
# dispatcher
# ---------------------------------------------------------------------------


def _layout(tmp_path: Path) -> dict[str, Any]:
    base = tmp_path.resolve()
    runs_dir = base / "worker-runs"
    runs_dir.mkdir()
    os.chmod(runs_dir, 0o2710)
    bin_dir = base / "bin"
    bin_dir.mkdir()
    os.chmod(bin_dir, 0o755)
    wrapper = bin_dir / "agy-worker-exec"
    shutil.copyfile(WRAPPER, wrapper)
    os.chmod(wrapper, 0o755)
    source_agy = base / "owner-bin" / "agy"
    source_agy.parent.mkdir()
    source_agy.write_text("#!/bin/sh\necho agy\n", encoding="utf-8")
    os.chmod(source_agy, 0o755)
    worker_agy = bin_dir / "agy"
    shutil.copyfile(source_agy, worker_agy)
    os.chmod(worker_agy, 0o755)
    home = base / "pool" / "google-07" / "home"
    for rel, text in ((TOKEN, "token"), (INSTALLATION_ID, "install-id")):
        (home / rel).parent.mkdir(parents=True, exist_ok=True)
        (home / rel).write_text(text, encoding="utf-8")
    (home / ".gemini" / "antigravity-cli" / "settings.json").write_text("{}\n", encoding="utf-8")
    target = base / "attempt"
    (target / "src").mkdir(parents=True)
    (target / "src" / "a.py").write_text("print('a')\n", encoding="utf-8")
    return {
        "runs": runs_dir,
        "wrapper": wrapper,
        "source_agy": source_agy,
        "worker_agy": worker_agy,
        "home": home,
        "target": target,
    }


@pytest.fixture
def worker_env(tmp_path, monkeypatch):
    """A temporary worker layout; the worker user and run group map to ourselves."""
    layout = _layout(tmp_path)
    gid = os.getgid()
    monkeypatch.setattr(worker_mod.pwd, "getpwnam", lambda name: object())
    monkeypatch.setattr(worker_mod.os, "getgroups", lambda: [gid])
    if not admission.seatbelt_available():
        monkeypatch.setattr(boundary_mod, "seatbelt_available", lambda: True)
    os.chown(layout["runs"], -1, gid)
    os.chmod(layout["runs"], 0o2710)
    layout["group"] = grp.getgrgid(gid).gr_name
    layout["gid"] = gid
    return layout


def _patch_prepare(monkeypatch, layout: dict[str, Any], run_command) -> None:
    monkeypatch.setattr(
        worker_mod,
        "prepare_worker_account_boundary",
        functools.partial(
            worker_mod.prepare_worker_account_boundary,
            runs_dir=layout["runs"],
            wrapper=layout["wrapper"],
            worker_agy=layout["worker_agy"],
            run_group=layout["group"],
            repo_wrapper=WRAPPER,
            run_command=run_command,
        ),
    )
    real_which = shutil.which
    monkeypatch.setattr(
        dispatch.shutil,
        "which",
        lambda name, *a, **k: (
            str(layout["source_agy"]) if name == "agy" else real_which(name, *a, **k)
        ),
    )
    monkeypatch.setattr(cli_worker, "sweep_run", lambda *a, **k: True)


class _Tracker:
    probe_failed = False

    def stop(self):
        return set()


def _launch(boundary) -> None:
    """What the real runner does to the boundary around a launch."""
    boundary.before_launch()
    boundary._launched = True
    boundary._tracker = _Tracker()
    (boundary.run_root / worker_mod.WRAPPER_STARTED_MARKER).write_text("", encoding="utf-8")


class _SweepRun:
    def __init__(self, stdout: str, returncode: int = 0) -> None:
        self.calls: list[list[str]] = []
        self.stdout, self.returncode = stdout, returncode

    def __call__(self, argv, **_kwargs):
        self.calls.append(list(argv))
        return subprocess.CompletedProcess(argv, self.returncode, self.stdout, "")


class _Claim:
    def __init__(self, home: Path, events: list[str], mark_error: Exception | None = None) -> None:
        self.account_alias_hash = "worker"
        self.lease_id_hash = "lease-worker"
        self.internal_id = "worker-account"
        self.lease = type(
            "Lease", (), {"execution_env": {"HOME": str(home), "PATH": "/usr/bin:/bin"}}
        )()
        self.released = False
        self.events = events
        self.marks: list[dict[str, Any]] = []
        self.mark_error = mark_error

    def mark_worker_run(self, *, run_root: str, run_root_id: list[int], run_as_user: str) -> None:
        self.events.append("mark")
        if self.mark_error is not None:
            raise self.mark_error
        self.marks.append({
            "run_root": run_root,
            "run_root_id": run_root_id,
            "run_as_user": run_as_user,
        })

    def release(self) -> None:
        self.events.append("release")
        self.released = True


class _Coordinator:
    def __init__(self, claim: _Claim) -> None:
        self.claim = claim
        self.acquire_count = 0

    def acquire_claim(self, **_kwargs):
        self.acquire_count += 1
        return self.claim


def _metas(err: str) -> list[dict[str, Any]]:
    prefix = "NEXUS_AGY_DISPATCH "
    return [json.loads(line[len(prefix) :]) for line in err.splitlines() if line.startswith(prefix)]


def _run_dispatch(layout: dict[str, Any], coordinator: Any, runner: Any, **extra: Any) -> int:
    target = layout["target"]
    return dispatch.dispatch_run(
        prompt="edit",
        cwd=str(target),
        mode="accept-edits",
        write_paths=[str(target / "src" / "a.py")],
        coordinator=coordinator,
        run_agy_fn=runner,
        run_as_user="_cairnwork_worker",
        **extra,
    )


def test_mark_happens_before_the_runner_starts_and_names_the_run_root(
    worker_env, monkeypatch, capsys
) -> None:
    _patch_prepare(monkeypatch, worker_env, _SweepRun(SWEEP_CLEAN))
    events: list[str] = []
    claim = _Claim(worker_env["home"], events)
    seen: dict[str, Any] = {}

    def runner(*, env, prompt, cwd, mode, model, effort, timeout, write_boundary):
        events.append("runner")
        info = os.lstat(write_boundary.run_root)
        seen["identity"] = [info.st_dev, info.st_ino]
        seen["root"] = str(write_boundary.run_root)
        _launch(write_boundary)
        return 0, "ok", "", False, 1

    assert _run_dispatch(worker_env, _Coordinator(claim), runner) == 0, _metas(
        capsys.readouterr().err
    )
    assert events == ["mark", "runner", "release"]
    assert claim.marks == [
        {
            "run_root": seen["root"],
            "run_root_id": seen["identity"],
            "run_as_user": "_cairnwork_worker",
        }
    ]
    assert claim.released is True  # a clean worker sweep still releases


def test_mark_happens_before_the_provider_popen(worker_env, monkeypatch, capsys) -> None:
    """With the real run_agy: mark, then ``Popen`` of the sudo wrapper, nothing earlier."""
    _patch_prepare(monkeypatch, worker_env, _SweepRun(SWEEP_CLEAN))
    events: list[str] = []
    claim = _Claim(worker_env["home"], events)
    launched: list[list[str]] = []

    class _Stop(Exception):
        pass

    real_popen = subprocess.Popen

    def fake_popen(argv, *args, **kwargs):
        # subprocess is one global module: only the provider launch is intercepted
        if not (isinstance(argv, list) and argv[:1] == ["/usr/bin/sudo"]):
            return real_popen(argv, *args, **kwargs)
        events.append("popen")
        launched.append(list(argv))
        raise _Stop()

    monkeypatch.setattr(dispatch.subprocess, "Popen", fake_popen)
    with pytest.raises(_Stop):
        _run_dispatch(worker_env, _Coordinator(claim), None)
    assert events[:2] == ["mark", "popen"]
    assert launched[0][:4] == ["/usr/bin/sudo", "-n", "-u", "_cairnwork_worker"]
    assert claim.marks[0]["run_root"] in launched[0]
    capsys.readouterr()


@pytest.mark.parametrize(
    "error",
    [
        AgyAccountPoolError("AGY_WORKER_LEASE_MARK_FAILED:OSError"),
        OSError("disk full"),
        AttributeError("claim cannot mark"),
    ],
    ids=["pool-error", "oserror", "attribute-error"],
)
def test_mark_failure_launches_nothing_and_does_not_rotate(
    worker_env, monkeypatch, capsys, error: Exception
) -> None:
    sweeps = _SweepRun(SWEEP_CLEAN)
    _patch_prepare(monkeypatch, worker_env, sweeps)
    events: list[str] = []
    claim = _Claim(worker_env["home"], events, mark_error=error)
    coordinator = _Coordinator(claim)
    runner_calls: list[Any] = []

    def runner(*, env, prompt, cwd, mode, model, effort, timeout, write_boundary):
        runner_calls.append(write_boundary)
        return 0, "ok", "", False, 1

    code = _run_dispatch(worker_env, coordinator, runner, max_calls=3)
    meta = _metas(capsys.readouterr().err)[-1]
    assert code == 1
    assert meta["status"] == "failed"
    assert meta["failure_kind"] == f"AGY_WORKER_LEASE_MARK_FAILED:{type(error).__name__}"
    assert meta["provider_effect"] is False and meta["reconciliation_required"] is False
    assert meta["rotations"] == 0 and coordinator.acquire_count == 1
    assert runner_calls == [] and sweeps.calls == []  # nothing launched, nothing to sweep
    assert list(worker_env["runs"].iterdir()) == []  # the boundary was cleaned up
    assert events == ["mark", "release"]  # unmarked claim: nothing could be running
    assert claim.released is True


def test_mark_failure_is_recorded_in_the_operation_hook(worker_env, monkeypatch) -> None:
    _patch_prepare(monkeypatch, worker_env, _SweepRun(SWEEP_CLEAN))
    claim = _Claim(worker_env["home"], [], mark_error=OSError("x"))
    payloads: list[dict[str, Any]] = []

    def runner(*, env, prompt, cwd, mode, model, effort, timeout, write_boundary):
        raise AssertionError("must not launch")

    code = _run_dispatch(worker_env, _Coordinator(claim), runner, operation_hook=payloads.append)
    assert code == 1
    failures = [p for p in payloads if str(p.get("failure_kind")).startswith("AGY_WORKER_LEASE")]
    assert failures and failures[-1]["provider_effect"] is False
    assert failures[-1]["failure_kind"] == "AGY_WORKER_LEASE_MARK_FAILED:OSError"
    assert failures[-1]["reconciliation_required"] is False
    # no "sweep pending" marker: nothing was launched, so there is nothing to sweep
    assert not any("descendant_sweep_clean" in p for p in payloads)


@pytest.mark.parametrize("with_marker", [True, False], ids=["runner-marker", "no-marker"])
def test_unclean_worker_sweep_never_releases_the_claim(
    worker_env, monkeypatch, capsys, with_marker: bool
) -> None:
    _patch_prepare(monkeypatch, worker_env, _SweepRun(SWEEP_UNCLEAN, 3))
    events: list[str] = []
    claim = _Claim(worker_env["home"], events)
    coordinator = _Coordinator(claim)
    boundaries: list[Any] = []

    def runner(*, env, prompt, cwd, mode, model, effort, timeout, write_boundary):
        boundaries.append(write_boundary)
        _launch(write_boundary)
        err = f"{dispatch.DESCENDANT_SWEEP_FAILED_MARKER}\n" if with_marker else ""
        return 0, "edited", err, False, 1

    code = _run_dispatch(worker_env, coordinator, runner, max_calls=3)
    meta = _metas(capsys.readouterr().err)[-1]
    assert code != 0
    assert meta["failure_kind"] == "AGY_DESCENDANT_SWEEP_FAILED"
    assert meta["reconciliation_required"] is True
    assert boundaries[0].sweep() is False
    assert claim.released is False and "release" not in events
    assert coordinator.acquire_count == 1 and meta["rotations"] == 0


def test_unclean_worker_sweep_after_a_raising_runner_keeps_the_claim(
    worker_env, monkeypatch
) -> None:
    _patch_prepare(monkeypatch, worker_env, _SweepRun(SWEEP_UNCLEAN, 3))
    claim = _Claim(worker_env["home"], [])

    def runner(*, env, prompt, cwd, mode, model, effort, timeout, write_boundary):
        _launch(write_boundary)
        raise KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        _run_dispatch(worker_env, _Coordinator(claim), runner)
    assert claim.released is False


def test_a_sweep_that_raises_counts_as_unclean(worker_env, monkeypatch, capsys) -> None:
    _patch_prepare(monkeypatch, worker_env, _SweepRun(SWEEP_CLEAN))
    claim = _Claim(worker_env["home"], [])

    def runner(*, env, prompt, cwd, mode, model, effort, timeout, write_boundary):
        _launch(write_boundary)

        def boom():
            raise RuntimeError("sweep exploded")

        monkeypatch.setattr(write_boundary, "sweep", boom)
        monkeypatch.setattr(write_boundary, "cleanup", lambda: None)
        return 0, "edited", "", False, 1

    with pytest.raises(RuntimeError, match="sweep exploded"):
        _run_dispatch(worker_env, _Coordinator(claim), runner)
    capsys.readouterr()
    assert claim.released is False  # an unprovable sweep never frees the account


def test_a_sweep_that_raised_in_cleanup_is_not_rerun_to_free_the_account(
    worker_env, monkeypatch, capsys
) -> None:
    # The first wrapper sweep raises inside cleanup(); a second call would come
    # back clean.  The release decision must read the recorded verdict (none)
    # instead of running the sweep again.
    _patch_prepare(monkeypatch, worker_env, _SweepRun(SWEEP_CLEAN))
    claim = _Claim(worker_env["home"], [])
    sweeps: list[int] = []

    def runner(*, env, prompt, cwd, mode, model, effort, timeout, write_boundary):
        _launch(write_boundary)

        def flaky(pids):
            sweeps.append(1)
            if len(sweeps) == 1:
                raise RuntimeError("sweep interrupted")
            return True

        monkeypatch.setattr(write_boundary, "_worker_sweep", flaky)
        return 0, "edited", "", False, 1

    with pytest.raises(RuntimeError, match="sweep interrupted"):
        _run_dispatch(worker_env, _Coordinator(claim), runner)
    capsys.readouterr()
    assert sweeps == [1]
    assert claim.released is False


def test_an_unlaunched_worker_attempt_still_releases(worker_env, monkeypatch, capsys) -> None:
    """A runner that fails before launching leaves nothing running: release as before."""
    _patch_prepare(monkeypatch, worker_env, _SweepRun(SWEEP_CLEAN))
    claim = _Claim(worker_env["home"], [])

    def runner(*, env, prompt, cwd, mode, model, effort, timeout, write_boundary):
        raise RuntimeError("AGY_BINARY_NOT_FOUND")

    with pytest.raises(RuntimeError, match="AGY_BINARY_NOT_FOUND"):
        _run_dispatch(worker_env, _Coordinator(claim), runner)
    capsys.readouterr()
    assert claim.released is True


def test_real_claim_keeps_a_marked_receipt_after_an_unclean_sweep(
    worker_env, tmp_path, monkeypatch, capsys, reap_clock
) -> None:
    """End to end with the real pool: the receipt survives and names the worker run."""
    _patch_prepare(monkeypatch, worker_env, _SweepRun(SWEEP_UNCLEAN, 3))
    monkeypatch.setenv("NEXUS_AGY_MODEL_CATALOG_CHECK", "0")
    for name in (
        "NEXUS_AGY_POOL_WAIT_TIMEOUT",
        "NEXUS_AGY_PREFERRED_ACCOUNTS",
        "NEXUS_AGY_RESERVE_ACCOUNTS",
        "NEXUS_AGY_FALLBACK_ACCOUNTS",
        "NEXUS_AGY_BLOCKED_ACCOUNTS",
    ):
        monkeypatch.delenv(name, raising=False)
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
    home = tmp_path / "pool-home"
    (home / TOKEN).parent.mkdir(parents=True)
    (home / TOKEN).write_text("token", encoding="utf-8")
    coordinator = CrossProcessLeaseCoordinator(
        manager=AgyAccountPoolManager(
            accounts=[AgyAccount(alias="a", home_dir=str(home))], use_real_manager=False
        ),
        allocator_lock_path=tmp_path / "allocator.lock",
        leases_dir=tmp_path / "leases",
        poll_interval=0.02,
    )
    claims: list[AccountLeaseClaim] = []
    real_acquire = coordinator.acquire_claim

    def acquire(**kwargs):
        claims.append(real_acquire(**kwargs))
        return claims[-1]

    monkeypatch.setattr(coordinator, "acquire_claim", acquire)
    seen: dict[str, Any] = {}

    def runner(*, env, prompt, cwd, mode, model, effort, timeout, write_boundary):
        receipts = list((tmp_path / "leases").glob("*.receipt.json"))
        assert len(receipts) == 1
        seen["during"] = _read(receipts[0])
        seen["root"] = str(write_boundary.run_root)
        info = os.lstat(write_boundary.run_root)
        seen["identity"] = [info.st_dev, info.st_ino]
        _launch(write_boundary)
        return 0, "edited", f"{dispatch.DESCENDANT_SWEEP_FAILED_MARKER}\n", False, 1

    code = _run_dispatch(
        worker_env, coordinator, runner, model="gemini-3.8-flash-high", max_calls=3
    )
    capsys.readouterr()
    assert code != 0
    during = seen["during"]
    assert during["worker_run_root"] == seen["root"]
    assert during["worker_run_root_id"] == seen["identity"]
    assert during["worker_run_as_user"] == "_cairnwork_worker"
    (claim,) = claims
    receipt = claim.receipt_path
    try:
        assert claim.released is False
        assert _read(receipt) == during  # still there, unchanged
        # The dispatcher exits: its lock fd closes, the pid is gone, the receipt stays.
        # The next claimer must ask the reaper; it keeps the account until proven gone.
        claim.lock_file_obj.close()
        data = _read(receipt)
        data["pid"] = _dead_pid()
        receipt.write_text(json.dumps(data) + "\n", encoding="utf-8")
        run_root = Path(seen["root"])
        assert run_root.exists()  # an unclean worker sweep keeps the run root (#2888)
        # The real reaper (fake sudo): the per-run wrapper sweep decides, not "no process".
        commands = _Commands(sweep=(3, SWEEP_UNCLEAN))
        real_reaper = worker_mod.reap_orphaned_worker_run
        monkeypatch.setattr(worker_mod, "WORKER_RUNS", worker_env["runs"].resolve())
        monkeypatch.setattr(
            worker_mod, "reap_orphaned_worker_run", lambda r: real_reaper(r, run_command=commands)
        )
        with pytest.raises(AgyAccountPoolBusyError):
            real_acquire(consumer_id="desktop-next", wait_timeout=0)
        assert receipt.exists() and run_root.exists()
        assert commands.sweeps == [worker_mod.sweep_argv(run_root, [])] and commands.pses == []
        commands.sweep = (0, SWEEP_CLEAN)
        reap_clock.now += agy_pool.WORKER_REAP_NEGATIVE_TTL_SECONDS + 1
        next_claim = real_acquire(consumer_id="desktop-next", wait_timeout=0)
        next_claim.release()
        assert not run_root.exists() and not receipt.exists()
    finally:
        if not claim.lock_file_obj.closed:
            claim.lock_file_obj.close()


def test_default_dispatch_never_marks(tmp_path, monkeypatch, capsys) -> None:
    """Without --run-as-user the claim is not asked to mark anything."""
    if not admission.seatbelt_available():
        monkeypatch.setattr(boundary_mod, "seatbelt_available", lambda: True)
    home = tmp_path.resolve() / "home"
    (home / TOKEN).parent.mkdir(parents=True)
    (home / TOKEN).write_text("token", encoding="utf-8")
    target = tmp_path.resolve() / "work"
    target.mkdir()
    events: list[str] = []
    claim = _Claim(home, events, mark_error=AssertionError("must not mark"))

    def runner(*, env, prompt, cwd, mode, model, effort, timeout, write_boundary):
        return 0, "ok", "", False, 1

    code = dispatch.dispatch_run(
        prompt="edit",
        cwd=str(target),
        mode="accept-edits",
        write_paths=[str(target / "a.py")],
        coordinator=_Coordinator(claim),
        run_agy_fn=runner,
    )
    capsys.readouterr()
    assert code == 0 and "mark" not in events and claim.released is True


# ---------------------------------------------------------------------------
# item 3: the default profile denies worker-runs, the worker profile is unchanged
# ---------------------------------------------------------------------------

HEAD = "(version 1)\n(allow default)\n"
RUNS_LITERAL = "/Users/Shared/cairnwork-worker/worker-runs"


def _sexprs(text: str) -> list:
    tokens = re.findall(r'#?"(?:[^"\\]|\\.)*"|[()]|[^\s()]+', re.sub(r";[^\n]*", "", text))
    stack: list[list] = [[]]
    for token in tokens:
        if token == "(":
            stack.append([])
        elif token == ")":
            done = stack.pop()
            stack[-1].append(done)
        else:
            stack[-1].append(token)
    assert len(stack) == 1
    return stack[0]


def _effective(profile: str, op: str, path: Path | str) -> str:
    """Last matching rule wins; enough for these profiles."""
    verdict = "deny"
    target = str(path)
    for form in _sexprs(profile):
        if not form or form[0] not in ("allow", "deny"):
            continue
        ops = [item for item in form[1:] if isinstance(item, str)]
        filters = [item for item in form[1:] if isinstance(item, list)]
        if "default" not in ops and not any(
            o == op or (o.endswith("*") and op.startswith(o[:-1])) for o in ops
        ):
            continue
        if not filters:
            verdict = form[0]
            continue
        for kind, *args in filters:
            value = args[0].strip('"') if args and args[0].startswith('"') else None
            if value is None:
                continue
            if (kind == "literal" and target == value) or (
                kind == "subpath" and (target == value or target.startswith(value + "/"))
            ):
                verdict = form[0]
    return verdict


def _default_boundary(tmp_path: Path, monkeypatch):
    if not admission.seatbelt_available():
        monkeypatch.setattr(boundary_mod, "seatbelt_available", lambda: True)
    home = tmp_path.resolve() / "home"
    (home / TOKEN).parent.mkdir(parents=True)
    (home / TOKEN).write_text("token", encoding="utf-8")
    target = tmp_path.resolve() / "work"
    target.mkdir()
    boundary = boundary_mod.prepare_accept_edits_boundary(
        source_env={"HOME": str(home), "PATH": "/usr/bin:/bin"}, target=target
    )
    return boundary, target


def test_worker_runs_constant_is_defined_once_and_matches_the_wrapper() -> None:
    assert str(boundary_mod.WORKER_RUNS_DIR) == RUNS_LITERAL
    assert worker_mod.WORKER_RUNS is boundary_mod.WORKER_RUNS_DIR
    assert worker_mod.WORKER_ROOT == worker_mod.WORKER_RUNS.parent
    assert worker_mod.WORKER_BIN == worker_mod.WORKER_ROOT / "bin"
    assert f"RUNS={RUNS_LITERAL}\n" in WRAPPER.read_text(encoding="utf-8")


def test_default_profile_denies_worker_runs_right_after_the_head(tmp_path, monkeypatch) -> None:
    boundary, target = _default_boundary(tmp_path, monkeypatch)
    try:
        profile = boundary.profile
        deny = f'(deny file-read* file-write* (subpath "{RUNS_LITERAL}"))\n'
        assert profile.startswith(HEAD)
        rest = profile[len(HEAD) :].splitlines(keepends=True)
        assert rest[0].startswith(";;") and rest[1] == deny  # the comment, then the rule
        assert profile.count(RUNS_LITERAL) == 1  # and nothing re-allows a path inside it
        for op in ("file-read*", "file-write*", "file-read-metadata"):
            assert _effective(profile, op, RUNS_LITERAL) == "deny", op
            assert _effective(profile, op, f"{RUNS_LITERAL}/{RUN_TAG}/home/x") == "deny", op
        # the rest of the profile is the unchanged #1912/#2202 profile
        assert _effective(profile, "file-write*", target / "a.py") == "allow"
        assert _effective(profile, "file-read*", target / "a.py") == "allow"
        assert _effective(profile, "file-write*", target / ".git" / "config") == "deny"
        for line in admission.LAUNCH_SERVICES_DENY_LINES:
            assert line in profile
    finally:
        boundary.cleanup()


def test_default_profile_only_differs_from_the_base_by_the_inserted_rule(
    tmp_path, monkeypatch
) -> None:
    boundary, target = _default_boundary(tmp_path, monkeypatch)
    try:
        home = tmp_path.resolve() / "home"
        base = admission.build_seatbelt_profile(
            run_root=boundary.run_root,
            writable_target=target,
            run_home=boundary.run_home,
            source_home=home,
        )
        assert boundary.profile == boundary_mod._deny_worker_runs(base)
        lines = boundary.profile.splitlines(keepends=True)
        assert "".join(lines[:2] + lines[4:]) == base  # head, (comment, rule), the rest
    finally:
        boundary.cleanup()


def test_deny_worker_runs_refuses_an_unexpected_profile_shape() -> None:
    with pytest.raises(ValueError, match="unexpected base profile shape"):
        boundary_mod._deny_worker_runs("(version 1)\n(deny default)\n")


def test_worker_profile_is_unchanged_and_has_no_blanket_rule_after_its_run_root_allow(
    worker_env,
) -> None:
    boundary = worker_mod.prepare_worker_account_boundary(
        source_env={"HOME": str(worker_env["home"]), "PATH": "/usr/bin:/bin"},
        target=worker_env["target"],
        worker_user=worker_mod.WORKER_USER,
        source_agy=str(worker_env["source_agy"]),
        runs_dir=worker_env["runs"],
        wrapper=worker_env["wrapper"],
        worker_agy=worker_env["worker_agy"],
        run_group=worker_env["group"],
        repo_wrapper=WRAPPER,
    )
    try:
        runs, run_root, work = worker_env["runs"], boundary.run_root, boundary.target
        base = admission.build_seatbelt_profile(
            run_root=run_root,
            writable_target=work,
            run_home=boundary.run_home,
            source_home=worker_env["home"],
        )
        # byte-identical to the construction at origin/main: cross_run_profile over the
        # unmodified base profile (worker_registry and this path never get the new rule)
        expected = worker_mod.cross_run_profile(
            base,
            runs_dir=runs,
            run_root=run_root,
            pinned_entries=(
                work,
                boundary.run_home,
                boundary.run_tmp,
                run_root / "agy-dispatch.sb",
            ),
        )
        assert boundary.profile == expected
        assert "#2888" not in boundary.profile
        lines = boundary.profile.splitlines()
        # the cross-run block is the first rule after the head, and the only deny of the runs dir
        assert lines[:2] == ["(version 1)", "(allow default)"]
        assert lines[2].startswith(";; Cairnwork #19 Phase B")
        assert lines[3] == f'(deny file-read* file-write* (subpath "{runs}"))'
        assert lines[4] == f'(allow file-read* (subpath "{run_root}"))'
        assert lines.count(f'(deny file-read* file-write* (subpath "{runs}"))') == 1
        # this run stays readable and writable, other runs do not
        assert _effective(boundary.profile, "file-read*", work / "src" / "a.py") == "allow"
        assert _effective(boundary.profile, "file-write*", work / "src" / "a.py") == "allow"
        assert _effective(boundary.profile, "file-read*", runs / ("0" * 32) / "x") == "deny"
    finally:
        boundary.cleanup()


def _seatbelt_usable() -> bool:
    if not admission.seatbelt_available():
        return False
    probe = subprocess.run(
        [admission.SANDBOX_EXEC_PATH, "-p", "(version 1) (allow default)", "/usr/bin/true"],
        capture_output=True,
        check=False,
    )
    return probe.returncode == 0


@darwin_witness
def test_default_profile_blocks_a_real_listing_of_a_worker_runs_dir(tmp_path, monkeypatch) -> None:
    """Live Seatbelt witness with a stand-in worker-runs dir (the real one needs the worker account)."""
    if not _seatbelt_usable():
        pytest.skip("sandbox-exec not usable here")
    runs_dir = tmp_path.resolve() / "stand-in-worker-runs"
    (runs_dir / RUN_TAG).mkdir(parents=True)
    (runs_dir / RUN_TAG / "secret").write_text("S", encoding="utf-8")
    other = tmp_path.resolve() / "elsewhere"
    other.mkdir()
    base = admission.build_seatbelt_profile(
        run_root=tmp_path.resolve() / "run", writable_target=None, run_home=None
    )
    profile_path = tmp_path / "default.sb"
    profile_path.write_text(boundary_mod._deny_worker_runs(base, runs_dir), encoding="utf-8")

    def run(*argv: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [admission.SANDBOX_EXEC_PATH, "-f", str(profile_path), *argv],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )

    denied = run("/bin/ls", str(runs_dir))
    assert denied.returncode != 0 and "Operation not permitted" in denied.stderr
    assert run("/bin/cat", str(runs_dir / RUN_TAG / "secret")).returncode != 0
    assert run("/bin/ls", str(other)).returncode == 0
    assert run("/bin/ls", "/tmp").returncode == 0


# ---------------------------------------------------------------------------
# review of #2904: worker receipts are reaped outside the allocation lock
# ---------------------------------------------------------------------------


def _lock_is_free(path: Path) -> bool:
    """True when another open file description can take this flock right now."""
    with path.open("a+") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        return True


def _alias_hash(alias: str) -> str:
    return AgyAccount(alias=alias, home_dir="/nowhere").alias_hash


def test_the_reaper_never_runs_under_the_allocation_lock(tmp_path: Path, monkeypatch) -> None:
    coordinator, alias_hash = _coordinator(tmp_path)
    old = _write_receipt(tmp_path, alias_hash, **_worker_fields())
    seen: list[dict[str, bool]] = []

    def fake_reaper(receipt, **_kwargs):
        seen.append({
            "allocation_lock_free": _lock_is_free(tmp_path / "allocator.lock"),
            "account_lock_free": _lock_is_free(tmp_path / "leases" / f"{alias_hash}.lock"),
            "receipt_still_there": old.exists(),
        })
        return True

    monkeypatch.setattr(worker_mod, "reap_orphaned_worker_run", fake_reaper)
    # A proven reap lets the very same call take the account on its next pass.
    claim = coordinator.acquire_claim("desktop-new", wait_timeout=0)
    try:
        assert claim.account_alias_hash == alias_hash
        assert _read(old)["consumer_id"] == "desktop-new" and "worker_run_root" not in _read(old)
    finally:
        claim.release()
    assert seen == [
        {"allocation_lock_free": True, "account_lock_free": False, "receipt_still_there": True}
    ]


def test_an_account_waiting_for_its_reap_counts_as_busy_but_another_is_still_claimable(
    tmp_path: Path, reaper
) -> None:
    coordinator, _first = _coordinator(tmp_path, aliases=("a", "b"))
    alias_a, alias_b = _alias_hash("a"), _alias_hash("b")
    _write_receipt(tmp_path, alias_a, **_worker_fields())
    reaper.result = False
    first = coordinator.acquire_claim("desktop-one", wait_timeout=0)
    try:
        # the free account is taken without ever reaping the other one's receipt
        assert first.account_alias_hash == alias_b and reaper.calls == []
        # with b held, a is only "busy" (not exhausted) until its run is proven gone
        with pytest.raises(AgyAccountPoolBusyError):
            coordinator.acquire_claim("desktop-two", wait_timeout=0)
        assert len(reaper.calls) == 1
    finally:
        first.release()


def test_an_unproven_reap_is_retried_at_most_once_per_minute_and_warns_once(
    tmp_path: Path, reaper, reap_clock, caplog
) -> None:
    coordinator, alias_hash = _coordinator(tmp_path)
    receipt = _write_receipt(tmp_path, alias_hash, **_worker_fields())
    reaper.result = False
    ttl = agy_pool.WORKER_REAP_NEGATIVE_TTL_SECONDS
    assert ttl == 60.0

    def attempt() -> None:
        with pytest.raises(AgyAccountPoolBusyError):
            coordinator.acquire_claim("desktop-new", wait_timeout=0)

    with caplog.at_level(logging.WARNING, logger="nexus.services.agy_account_pool"):
        attempt()
        assert len(reaper.calls) == 1
        reap_clock.now += ttl - 1
        attempt()
        attempt()
        assert len(reaper.calls) == 1  # still inside the minute
        reap_clock.now += 2
        attempt()
        assert len(reaper.calls) == 2  # retried once the minute is over
        attempt()
        assert len(reaper.calls) == 2
    assert caplog.text.count("AGY_ORPHANED_WORKER_RECEIPT_PRESERVED") == 1  # first result only
    assert receipt.exists()
    reaper.result = True  # once the run is proven gone the account is claimable again
    reap_clock.now += ttl + 1
    claim = coordinator.acquire_claim("desktop-new", wait_timeout=0)
    claim.release()
    assert len(reaper.calls) == 3


def test_polling_an_unproven_receipt_neither_re_reaps_nor_re_logs(
    tmp_path: Path, reaper, reap_clock, caplog
) -> None:
    coordinator, alias_hash = _coordinator(tmp_path, poll_interval=0.01)
    _write_receipt(tmp_path, alias_hash, **_worker_fields())
    reaper.result = False
    with caplog.at_level(logging.WARNING, logger="nexus.services.agy_account_pool"):
        with pytest.raises(AgyAccountPoolBusyError):
            coordinator.acquire_claim("desktop-new", wait_timeout=0.3)  # ~30 polls
    assert len(reaper.calls) == 1
    assert caplog.text.count("AGY_ORPHANED_WORKER_RECEIPT_PRESERVED") == 1


def test_a_deferred_reap_rechecks_the_account_lock_and_the_receipt(tmp_path: Path, reaper) -> None:
    coordinator, alias_hash = _coordinator(tmp_path)
    receipt = _write_receipt(tmp_path, alias_hash, **_worker_fields())
    entry = (alias_hash, receipt, "deadbeef0001")
    reaper.result = True
    lock_path = tmp_path / "leases" / f"{alias_hash}.lock"
    with lock_path.open("a+") as holder:  # someone claimed the account meanwhile
        fcntl.flock(holder.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert coordinator._reap_deferred_worker_receipts([entry]) is False
    assert reaper.calls == [] and receipt.exists()

    data = _read(receipt)
    other = dict(data, lease_id_hash="feedface0002")  # the receipt changed hands
    receipt.write_text(json.dumps(other) + "\n", encoding="utf-8")
    assert coordinator._reap_deferred_worker_receipts([entry]) is False
    alive = dict(data, pid=os.getppid())  # its owner is alive after all
    receipt.write_text(json.dumps(alive) + "\n", encoding="utf-8")
    assert coordinator._reap_deferred_worker_receipts([entry]) is False
    assert reaper.calls == [] and receipt.exists()

    receipt.write_text(json.dumps(data) + "\n", encoding="utf-8")  # exactly what was deferred
    assert coordinator._reap_deferred_worker_receipts([entry]) is True
    assert len(reaper.calls) == 1 and not receipt.exists()
    assert _lock_is_free(lock_path)  # the per-account flock is released again


# ---------------------------------------------------------------------------
# review of #2904: the other receipt-removal paths need the reaper as well
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        pytest.param(False, "LEASE_WORKER_UNPROVEN_PRESERVED", id="not-proven"),
        pytest.param(RuntimeError("boom"), "LEASE_WORKER_UNPROVEN_PRESERVED", id="reaper-raises"),
        pytest.param(True, "LEASE_RECEIPT_REMOVED", id="proven"),
    ],
)
def test_pool_reconcile_claim_receipt_needs_the_reaper_for_worker_receipts(
    tmp_path: Path, reaper, result: Any, expected: str
) -> None:
    coordinator, alias_hash = _coordinator(tmp_path)
    receipt = _write_receipt(tmp_path, alias_hash, **_worker_fields())
    reaper.result = result
    outcome = coordinator.reconcile_claim_receipt(
        account_alias_hash=alias_hash,
        lease_id_hash="deadbeef0001",
        owner_pid=_read(receipt)["pid"],
    )
    assert outcome == {"result": expected}
    assert receipt.exists() is (expected != "LEASE_RECEIPT_REMOVED")
    assert len(reaper.calls) == 1


def test_pool_reconcile_claim_receipt_without_worker_fields_never_calls_the_reaper(
    tmp_path: Path, reaper
) -> None:
    coordinator, alias_hash = _coordinator(tmp_path)
    receipt = _write_receipt(tmp_path, alias_hash)
    outcome = coordinator.reconcile_claim_receipt(
        account_alias_hash=alias_hash,
        lease_id_hash="deadbeef0001",
        owner_pid=_read(receipt)["pid"],
    )
    assert outcome == {"result": "LEASE_RECEIPT_REMOVED"} and reaper.calls == []


def _reconciled_record(alias_hash: str, owner_pid: int) -> dict[str, Any]:
    return {
        "reconciliation": {"provider_alive_after": False},
        "account_alias_hash": alias_hash,
        "lease_id_hash": "deadbeef0001",
        "pid": owner_pid,
    }


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        pytest.param(False, "LEASE_WORKER_UNPROVEN_PRESERVED", id="not-proven"),
        pytest.param(OSError("boom"), "LEASE_WORKER_UNPROVEN_PRESERVED", id="reaper-raises"),
        pytest.param(True, "LEASE_RECEIPT_REMOVED", id="proven"),
    ],
)
def test_dispatcher_lease_cleanup_needs_the_reaper_for_worker_receipts(
    tmp_path: Path, monkeypatch, reaper, result: Any, expected: str
) -> None:
    coordinator, alias_hash = _coordinator(tmp_path)
    receipt = _write_receipt(tmp_path, alias_hash, **_worker_fields())
    monkeypatch.setattr(dispatch, "LEASES_DIR", tmp_path / "leases")
    reaper.result = result
    outcome = dispatch._cleanup_reconciled_lease(
        _reconciled_record(alias_hash, _read(receipt)["pid"])
    )
    assert outcome == {"result": expected}
    assert receipt.exists() is (expected != "LEASE_RECEIPT_REMOVED")
    assert len(reaper.calls) == 1


def test_dispatcher_lease_cleanup_without_worker_fields_never_calls_the_reaper(
    tmp_path: Path, monkeypatch, reaper
) -> None:
    coordinator, alias_hash = _coordinator(tmp_path)
    receipt = _write_receipt(tmp_path, alias_hash)
    monkeypatch.setattr(dispatch, "LEASES_DIR", tmp_path / "leases")
    outcome = dispatch._cleanup_reconciled_lease(
        _reconciled_record(alias_hash, _read(receipt)["pid"])
    )
    assert outcome == {"result": "LEASE_RECEIPT_REMOVED"} and reaper.calls == []
    assert not receipt.exists()


# ---------------------------------------------------------------------------
# review of #2904: the launch window, and the run root of an unproven sweep
# ---------------------------------------------------------------------------


def _prepare_boundary(layout: dict[str, Any], run_command) -> Any:
    return worker_mod.prepare_worker_account_boundary(
        source_env={"HOME": str(layout["home"]), "PATH": "/usr/bin:/bin"},
        target=layout["target"],
        worker_user=worker_mod.WORKER_USER,
        source_agy=str(layout["source_agy"]),
        runs_dir=layout["runs"],
        wrapper=layout["wrapper"],
        worker_agy=layout["worker_agy"],
        run_group=layout["group"],
        repo_wrapper=WRAPPER,
        run_command=run_command,
    )


def _worker_receipts_in(err: str) -> list[dict[str, Any]]:
    prefix = "NEXUS_AGY_DISPATCH "
    found = [
        json.loads(line[len(prefix) :]) for line in err.splitlines() if line.startswith(prefix)
    ]
    return [meta for meta in found if str(meta.get("event", "")).startswith("WORKER_")]


@pytest.mark.parametrize("clean", [False, True], ids=["unclean-sweep", "clean-sweep"])
def test_a_launch_that_was_attempted_counts_as_launched_before_after_launch(
    worker_env, monkeypatch, clean: bool
) -> None:
    monkeypatch.setattr(cli_worker, "sweep_run", lambda *a, **k: True)
    run = _SweepRun(SWEEP_CLEAN if clean else SWEEP_UNCLEAN, 0 if clean else 3)
    boundary = _prepare_boundary(worker_env, run)
    # nothing attempted yet: free, and no sweep is run for a boundary that never launched
    assert boundary.sweep_verdict_clean is True
    assert boundary.sweep() is True and run.calls == []
    boundary.before_launch()  # Popen runs next; after_launch has not
    assert boundary._launched is False
    assert boundary.sweep_verdict_clean is False  # no verdict yet: the account is not free
    boundary.cleanup()  # what a signal in this window ends up running
    assert run.calls == [
        worker_mod.sweep_argv(boundary.run_root, [], wrapper=worker_env["wrapper"])
    ]
    assert boundary.sweep_verdict_clean is clean
    assert boundary.run_root.exists() is (not clean)
    if not clean:
        shutil.rmtree(boundary.run_root)


@pytest.mark.parametrize(
    ("sweep", "released"),
    [
        pytest.param((3, SWEEP_UNCLEAN), False, id="unclean-sweep"),
        pytest.param((0, SWEEP_CLEAN), True, id="clean-sweep"),
    ],
)
def test_a_signal_between_popen_and_after_launch_is_judged_by_the_worker_sweep(
    worker_env, monkeypatch, capsys, sweep: tuple[int, str], released: bool
) -> None:
    _patch_prepare(monkeypatch, worker_env, _SweepRun(sweep[1], sweep[0]))
    claim = _Claim(worker_env["home"], [])

    def runner(*, env, prompt, cwd, mode, model, effort, timeout, write_boundary):
        write_boundary.before_launch()
        # Popen returned, then the signal arrived before after_launch recorded the launch
        raise KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        _run_dispatch(worker_env, _Coordinator(claim), runner)
    capsys.readouterr()
    assert claim.released is released


def test_an_interrupt_after_the_owner_side_sweep_never_leaves_a_clean_verdict(
    worker_env, monkeypatch
) -> None:
    monkeypatch.setattr(cli_worker, "sweep_run", lambda *a, **k: True)
    boundary = _prepare_boundary(worker_env, _SweepRun(SWEEP_CLEAN))
    _launch(boundary)
    real_sweep = boundary_mod.AgyDispatchBoundary.sweep

    def interrupted(self):
        real_sweep(self)  # stores the Owner-side verdict (True) in ``_swept`` ...
        raise KeyboardInterrupt()  # ... and the combined verdict never gets computed

    monkeypatch.setattr(boundary_mod.AgyDispatchBoundary, "sweep", interrupted)
    with pytest.raises(KeyboardInterrupt):
        boundary.sweep()
    assert boundary._swept is None
    assert boundary.sweep_verdict_clean is False
    monkeypatch.setattr(boundary_mod.AgyDispatchBoundary, "sweep", real_sweep)
    boundary.cleanup()
    assert boundary.sweep_verdict_clean is False  # the tracker is spent: still not provable
    assert boundary.run_root.exists()
    shutil.rmtree(boundary.run_root)


def test_an_unclean_sweep_keeps_the_run_root_and_says_so(worker_env, monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli_worker, "sweep_run", lambda *a, **k: True)
    boundary = _prepare_boundary(worker_env, _SweepRun(SWEEP_UNCLEAN, 3))
    boundary.receipt_context = {"operation_id": None, "attempt": 1}
    _launch(boundary)
    (boundary.target / "src" / "a.py").write_text("worker edit\n", encoding="utf-8")
    boundary.cleanup()
    err = capsys.readouterr().err
    assert boundary.run_root.exists()
    assert boundary.leftover_run_root == str(boundary.run_root)
    assert f"worker run dir left behind: {boundary.run_root}" in err
    cleanup = [m for m in _worker_receipts_in(err) if m["event"] == "WORKER_CLEANUP"]
    assert [m["run_root_removed"] for m in cleanup] == [False]
    # copy-back stays skipped for an unclean sweep
    assert (worker_env["target"] / "src" / "a.py").read_text() == "print('a')\n"
    shutil.rmtree(boundary.run_root)


@pytest.mark.parametrize("clean", [False, True], ids=["unclean-sweep", "clean-sweep"])
def test_keep_run_root_env_behaviour_is_unchanged(worker_env, monkeypatch, clean: bool) -> None:
    monkeypatch.setenv(boundary_mod.KEEP_RUN_ROOT_ENV, "1")
    monkeypatch.setattr(cli_worker, "sweep_run", lambda *a, **k: True)
    run = _SweepRun(SWEEP_CLEAN if clean else SWEEP_UNCLEAN, 0 if clean else 3)
    boundary = _prepare_boundary(worker_env, run)
    _launch(boundary)
    boundary.cleanup()
    assert boundary.run_root.exists() and boundary.leftover_run_root is None
    shutil.rmtree(boundary.run_root)


def test_a_clean_sweep_still_removes_the_run_root(worker_env, monkeypatch) -> None:
    monkeypatch.setattr(cli_worker, "sweep_run", lambda *a, **k: True)
    boundary = _prepare_boundary(worker_env, _SweepRun(SWEEP_CLEAN))
    _launch(boundary)
    boundary.cleanup()
    assert not boundary.run_root.exists() and boundary.leftover_run_root is None


def test_worker_failure_with_an_unproven_sweep_ends_in_reconciliation_and_keeps_the_claim(
    worker_env, monkeypatch, capsys
) -> None:
    """No runner marker, a launch failure named, and a wrapper that reports survivors."""
    _patch_prepare(monkeypatch, worker_env, _SweepRun("AGY_WORKER_SWEEP unclean 42\n", 3))
    events: list[str] = []
    claim = _Claim(worker_env["home"], events)
    coordinator = _Coordinator(claim)
    boundaries: list[Any] = []

    def runner(*, env, prompt, cwd, mode, model, effort, timeout, write_boundary):
        boundaries.append(write_boundary)
        write_boundary.before_launch()
        write_boundary._launched = True
        write_boundary._tracker = _Tracker()
        # the wrapper-start marker is deliberately not written
        return 0, "edited", "", False, 1

    code = _run_dispatch(worker_env, coordinator, runner, max_calls=3)
    meta = _metas(capsys.readouterr().err)[-1]
    assert boundaries[0].worker_failure == "AGY_WORKER_LAUNCH_FAILED:wrapper_did_not_start"
    assert boundaries[0].sweep_verdict_clean is False
    assert code != 0
    assert meta["failure_kind"] == "AGY_DESCENDANT_SWEEP_FAILED"
    assert meta["reconciliation_required"] is True and meta["provider_effect"] is None
    assert meta["rotations"] == 0 and coordinator.acquire_count == 1
    assert claim.released is False and "release" not in events


# ---------------------------------------------------------------------------
# review of #2904: a target that overlaps worker-runs would re-open it
# ---------------------------------------------------------------------------


@pytest.fixture
def stand_in(tmp_path, monkeypatch):
    """A stand-in /Users/Shared/cairnwork-worker tree and a private TMPDIR."""
    base = tmp_path.resolve()
    shared = base / "Shared"
    runs_dir = shared / "cairnwork-worker" / "worker-runs"
    (runs_dir / RUN_TAG / "work").mkdir(parents=True)
    (runs_dir / RUN_TAG / "work" / "seed").write_text("secret\n", encoding="utf-8")
    sibling = shared / "cairnwork-worker" / "worker-runs-other"
    sibling.mkdir()
    normal = base / "normal-target"
    normal.mkdir()
    home = base / "home"
    (home / TOKEN).parent.mkdir(parents=True)
    (home / TOKEN).write_text("token", encoding="utf-8")
    private_tmp = base / "private-tmp"
    private_tmp.mkdir()
    monkeypatch.setattr(boundary_mod, "WORKER_RUNS_DIR", runs_dir)
    monkeypatch.setattr(tempfile, "tempdir", str(private_tmp))
    if not admission.seatbelt_available():
        monkeypatch.setattr(boundary_mod, "seatbelt_available", lambda: True)
    return SimpleNamespace(
        base=base,
        shared=shared,
        runs=runs_dir,
        sibling=sibling,
        normal=normal,
        tmp=private_tmp,
        env={"HOME": str(home), "PATH": "/usr/bin:/bin"},
    )


@pytest.mark.parametrize("which", ["ancestor", "equal", "descendant", "symlink-to-ancestor"])
def test_default_boundary_refuses_a_target_overlapping_worker_runs(stand_in, which: str) -> None:
    target = {
        "ancestor": stand_in.shared,
        "equal": stand_in.runs,
        "descendant": stand_in.runs / RUN_TAG / "work",
        "symlink-to-ancestor": stand_in.base / "link",
    }[which]
    if which == "symlink-to-ancestor":
        target.symlink_to(stand_in.shared)
    with pytest.raises(boundary_mod.AgyWriteBoundaryError) as excinfo:
        boundary_mod.prepare_accept_edits_boundary(source_env=stand_in.env, target=target)
    assert str(excinfo.value) == "AGY_WRITE_BOUNDARY_UNAVAILABLE:target_overlaps_worker_runs"
    assert list(stand_in.tmp.iterdir()) == []  # refused before anything was created


def test_default_boundary_allows_a_sibling_that_only_shares_the_prefix(stand_in) -> None:
    boundary = boundary_mod.prepare_accept_edits_boundary(
        source_env=stand_in.env, target=stand_in.sibling
    )
    try:
        assert boundary.target == stand_in.sibling
        assert f'(subpath "{stand_in.runs}")' in boundary.profile
    finally:
        boundary.cleanup()


def test_default_boundary_refuses_a_literal_write_grant_inside_worker_runs(stand_in) -> None:
    with pytest.raises(boundary_mod.AgyWriteBoundaryError) as excinfo:
        boundary_mod.prepare_accept_edits_boundary(
            source_env=stand_in.env,
            target=stand_in.normal,
            extra_writable_files=[stand_in.runs / "dispatch.log"],
            extra_writable_roots=[stand_in.runs],
        )
    assert str(excinfo.value) == "AGY_WRITE_BOUNDARY_UNAVAILABLE:extra_path_in_worker_runs"
    assert list(stand_in.tmp.iterdir()) == []


@darwin_witness
def test_default_profile_denies_real_writes_and_reads_under_worker_runs(stand_in) -> None:
    if not _seatbelt_usable():
        pytest.skip("sandbox-exec not usable here")
    boundary = boundary_mod.prepare_accept_edits_boundary(
        source_env=stand_in.env, target=stand_in.normal
    )
    try:

        def sandboxed(script: str) -> subprocess.CompletedProcess:
            return subprocess.run(
                [
                    admission.SANDBOX_EXEC_PATH,
                    "-f",
                    str(boundary.profile_path),
                    "/bin/sh",
                    "-c",
                    script,
                ],
                cwd="/",
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )

        planted = stand_in.runs / RUN_TAG / "work" / "planted"
        denied = sandboxed(f"echo x > '{planted}'")
        assert denied.returncode != 0 and "Operation not permitted" in denied.stderr
        assert not planted.exists()
        peek = sandboxed(f"cat '{stand_in.runs / RUN_TAG / 'work' / 'seed'}'")
        assert peek.returncode != 0 and "secret" not in peek.stdout
        ok = sandboxed(f"echo x > '{stand_in.normal}/ok' && echo WROTE")
        assert "WROTE" in ok.stdout and (stand_in.normal / "ok").exists()
    finally:
        boundary.cleanup()
