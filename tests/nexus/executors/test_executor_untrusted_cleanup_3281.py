"""Executor cleanup of directories a worker CLI wrote to uses the shared untrusted-tree
removal (#3281): a deep tree with a locked leaf is removed, and a removal that fails is
logged instead of staying silent. Host-side only, so these run on every platform."""

from __future__ import annotations

import logging
import os
import sys
import tempfile
import time
from pathlib import Path

from nexus.executors import agy_dispatch_boundary, agy_worker_account, cli_worker, codex_executor
from nexus.executors.cli_worker import CliWorkerRequest, run_cli_worker
from nexus.executors.codex_executor import CodexCliExecutor
from tests.nexus.executors.test_codex_executor import _contract, _lease

_DEPTH = 150
_FAILED = "tree_not_removed:forced"


def _deep_locked_tree(private: Path, depth: int = _DEPTH) -> Path:
    private.mkdir()
    fd = os.open(private, os.O_RDONLY)
    try:
        for _ in range(depth):
            os.mkdir("d", dir_fd=fd)
            nxt = os.open("d", os.O_RDONLY, dir_fd=fd)
            os.close(fd)
            fd = nxt
        os.chmod(fd, 0)
    finally:
        os.close(fd)
    return private


def _fail_removal(monkeypatch, module):
    seen: list[object] = []

    def refuse(path):
        seen.append(path)
        return _FAILED

    monkeypatch.setattr(module, "remove_untrusted_tree_quietly", refuse)
    return seen


def _isolated_home_factory(tmp_path: Path, prefix: str, made: list[Path]):
    real = tempfile.mkdtemp

    def mkdtemp(*args, **kwargs):
        if kwargs.get("prefix") == prefix:
            made.append(_deep_locked_tree(tmp_path / "home"))
            return str(made[-1])
        return real(*args, **kwargs)

    return mkdtemp


def _run_noop(tmp_path: Path) -> None:
    script = tmp_path / "noop.py"
    script.write_text("pass\n")
    result = run_cli_worker(
        CliWorkerRequest(
            executable=sys.executable, argv=(str(script),), cwd=str(tmp_path), timeout_seconds=30
        )
    )
    assert result.exit_code == 0, result.stderr


def test_cli_worker_isolated_home_deep_locked_tree_is_removed(tmp_path, monkeypatch):
    made: list[Path] = []
    monkeypatch.setattr(
        cli_worker.tempfile,
        "mkdtemp",
        _isolated_home_factory(tmp_path, "nexus-cli-worker-home-", made),
    )
    _run_noop(tmp_path)
    assert made and not made[0].exists()
    assert list(tmp_path.glob("home.stale-*")) == []


def test_cli_worker_isolated_home_cleanup_failure_is_logged(tmp_path, monkeypatch, caplog):
    seen = _fail_removal(monkeypatch, cli_worker)
    with caplog.at_level(logging.WARNING, logger=cli_worker.__name__):
        _run_noop(tmp_path)
    assert seen
    assert _FAILED in caplog.text


def _codex_invoke(tmp_path: Path, monkeypatch) -> None:
    contract = _contract(tmp_path)
    lease = _lease(tmp_path, contract)
    monkeypatch.setattr(codex_executor, "materialize_codex_home", lambda home: "refused_for_test")
    CodexCliExecutor().invoke(contract, lease, prompt="x")


def test_codex_run_home_deep_locked_tree_is_removed(tmp_path, monkeypatch):
    made: list[Path] = []
    monkeypatch.setattr(
        codex_executor.tempfile,
        "mkdtemp",
        _isolated_home_factory(tmp_path, "nexus-codex-home-", made),
    )
    _codex_invoke(tmp_path, monkeypatch)
    assert made and not made[0].exists()


def test_codex_run_home_cleanup_failure_is_logged(tmp_path, monkeypatch, caplog):
    seen = _fail_removal(monkeypatch, codex_executor)
    with caplog.at_level(logging.WARNING, logger=codex_executor.__name__):
        _codex_invoke(tmp_path, monkeypatch)
    assert seen
    assert _FAILED in caplog.text


def _bare_boundary(cls, run_root: Path, tmp_path: Path):
    boundary = object.__new__(cls)
    boundary.run_root = run_root
    boundary.profile_path = tmp_path / "profile-dir" / "p.sb"
    boundary.run_tag = "a" * 32
    boundary._launched = False
    boundary._launch_attempted = False
    boundary._swept = None
    boundary._tracker = None
    boundary._emit_cleanup_receipt = lambda: None
    return boundary


def test_agy_dispatch_boundary_cleanup_removes_deep_locked_run_root(tmp_path, monkeypatch):
    monkeypatch.delenv(agy_dispatch_boundary.KEEP_RUN_ROOT_ENV, raising=False)
    monkeypatch.setattr(cli_worker, "release_run", lambda tag: None)
    run_root = _deep_locked_tree(tmp_path / "run")
    boundary = _bare_boundary(agy_dispatch_boundary.AgyDispatchBoundary, run_root, tmp_path)
    boundary.cleanup()
    assert not run_root.exists()


def test_agy_dispatch_boundary_cleanup_failure_is_logged(tmp_path, monkeypatch, caplog):
    monkeypatch.delenv(agy_dispatch_boundary.KEEP_RUN_ROOT_ENV, raising=False)
    monkeypatch.setattr(cli_worker, "release_run", lambda tag: None)
    seen = _fail_removal(monkeypatch, agy_dispatch_boundary)
    run_root = tmp_path / "run"
    run_root.mkdir()
    boundary = _bare_boundary(agy_dispatch_boundary.AgyDispatchBoundary, run_root, tmp_path)
    with caplog.at_level(logging.WARNING, logger=agy_dispatch_boundary.__name__):
        boundary.cleanup()
    assert seen == [run_root]
    assert _FAILED in caplog.text


def test_agy_worker_boundary_cleanup_removes_deep_locked_run_root(tmp_path, monkeypatch):
    monkeypatch.delenv(agy_worker_account.KEEP_RUN_ROOT_ENV, raising=False)
    monkeypatch.setattr(cli_worker, "release_run", lambda tag: None)
    run_root = _deep_locked_tree(tmp_path / "run")
    boundary = _bare_boundary(agy_worker_account.AgyWorkerAccountBoundary, run_root, tmp_path)
    boundary.leftover_run_root = None
    boundary.cleanup()
    assert not run_root.exists()
    assert boundary.leftover_run_root is None


def test_agy_worker_boundary_cleanup_failure_is_logged(tmp_path, monkeypatch, caplog):
    monkeypatch.delenv(agy_worker_account.KEEP_RUN_ROOT_ENV, raising=False)
    monkeypatch.setattr(cli_worker, "release_run", lambda tag: None)
    seen = _fail_removal(monkeypatch, agy_worker_account)
    run_root = tmp_path / "run"
    run_root.mkdir()
    boundary = _bare_boundary(agy_worker_account.AgyWorkerAccountBoundary, run_root, tmp_path)
    boundary.leftover_run_root = None
    with caplog.at_level(logging.WARNING, logger=agy_worker_account.__name__):
        boundary.cleanup()
    assert seen == [run_root]
    assert "AGY_WORKER_RUN_ROOT_REMOVE_FAILED" in caplog.text


def _gc_setup(tmp_path: Path, monkeypatch, *, deep: bool) -> Path:
    runs = tmp_path / "runs"
    runs.mkdir()
    root = runs / ("b" * 32)
    if deep:
        _deep_locked_tree(root)
    else:
        root.mkdir()
    os.utime(root, (1, 1))
    monkeypatch.setattr(agy_worker_account, "_worker_user_has_no_process", lambda *a, **k: True)
    monkeypatch.setattr(agy_worker_account, "sweep_run_root", lambda *a, **k: "CLEAN")
    monkeypatch.delenv(agy_worker_account.KEEP_RUN_ROOT_ENV, raising=False)
    return runs


def test_agy_orphan_gc_removes_deep_locked_run_root(tmp_path, monkeypatch):
    runs = _gc_setup(tmp_path, monkeypatch, deep=True)
    agy_worker_account.gc_unreferenced_worker_run_roots(
        set(), runs_dir=runs, now=time.time() + 10**6
    )
    assert not (runs / ("b" * 32)).exists()


def test_agy_orphan_gc_removal_failure_is_logged(tmp_path, monkeypatch, caplog):
    runs = _gc_setup(tmp_path, monkeypatch, deep=False)
    seen = _fail_removal(monkeypatch, agy_worker_account)
    with caplog.at_level(logging.WARNING, logger=agy_worker_account.__name__):
        agy_worker_account.gc_unreferenced_worker_run_roots(
            set(), runs_dir=runs, now=time.time() + 10**6
        )
    assert len(seen) == 1
    assert "AGY_WORKER_ORPHAN_RUN_ROOT_REMOVE_FAILED" in caplog.text


def _reap_setup(tmp_path: Path, monkeypatch, *, deep: bool):
    runs = _gc_setup(tmp_path, monkeypatch, deep=deep)
    root = runs / ("b" * 32)
    info = root.lstat()
    monkeypatch.setattr(agy_worker_account, "WORKER_RUNS", runs)
    receipt = {
        "worker_run_as_user": agy_worker_account.WORKER_USER,
        "worker_run_root": str(root.resolve()),
        "worker_run_root_id": [info.st_dev, info.st_ino],
    }
    return root, receipt


def test_agy_reaper_removes_deep_locked_run_root(tmp_path, monkeypatch):
    root, receipt = _reap_setup(tmp_path, monkeypatch, deep=True)
    assert agy_worker_account.reap_orphaned_worker_run(receipt) is True
    assert not root.exists()


def test_agy_reaper_removal_failure_is_logged(tmp_path, monkeypatch, caplog):
    root, receipt = _reap_setup(tmp_path, monkeypatch, deep=False)
    seen = _fail_removal(monkeypatch, agy_worker_account)
    with caplog.at_level(logging.WARNING, logger=agy_worker_account.__name__):
        assert agy_worker_account.reap_orphaned_worker_run(receipt) is True
    assert seen
    assert "AGY_WORKER_RUN_ROOT_REMOVE_FAILED" in caplog.text
