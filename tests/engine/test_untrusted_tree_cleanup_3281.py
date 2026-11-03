"""Shared untrusted-tree cleanup (#3281) and the cleanup-failure error type of the model
sandbox (#3267). Host-side only: no OS sandbox is needed, so these run on every platform."""

from __future__ import annotations

import os
import subprocess
import sys
from contextlib import contextmanager

import pytest

import nexus.engine.model_output_sandbox as mos
import nexus.engine.untrusted_tree_cleanup as utc


def _deep_locked_tree(private, depth):
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


def test_missing_path_is_not_an_error(tmp_path):
    utc.remove_untrusted_tree(tmp_path / "absent")
    assert utc.remove_untrusted_tree_quietly(tmp_path / "absent") is None


def test_deep_tree_with_a_locked_leaf_is_removed(tmp_path, monkeypatch):
    monkeypatch.setattr(utc, "_WALK_MAX_OPEN", 4)
    tree = tmp_path / "t"
    _deep_locked_tree(tree, 200)
    utc.remove_untrusted_tree(tree)
    assert not tree.exists()
    assert list(tmp_path.glob("t.stale-*")) == []


def test_tree_that_cannot_be_removed_is_set_aside_and_reported(tmp_path, monkeypatch):
    tree = tmp_path / "t"
    tree.mkdir()
    (tree / "x").write_text("x")
    real = utc.shutil.rmtree

    def refused(path, *a, **k):
        raise OSError(1, "Operation not permitted", str(path))

    monkeypatch.setattr(utc.shutil, "rmtree", refused)
    aside = tmp_path / f"t.stale-{os.getpid()}"
    try:
        err = utc.remove_untrusted_tree_quietly(tree)
        assert err == f"tree_not_removed:{aside.name}"
        assert not tree.exists() and aside.is_dir()
    finally:
        monkeypatch.undo()
        if aside.exists():
            real(aside)


def test_quiet_variant_reports_recursion_error(tmp_path, monkeypatch):
    tree = tmp_path / "t"
    tree.mkdir()
    real = utc.shutil.rmtree

    def overflow(path, *a, **k):
        raise RecursionError("deep")

    monkeypatch.setattr(utc.shutil, "rmtree", overflow)
    aside = tmp_path / f"t.stale-{os.getpid()}"
    try:
        assert utc.remove_untrusted_tree_quietly(tree) == f"tree_not_removed:{aside.name}"
    finally:
        monkeypatch.undo()
        if aside.exists():
            real(aside)


@pytest.fixture
def stuck_private_area(tmp_path, monkeypatch):
    """A fake ``model_sandbox`` whose private area cannot be removed when the block ends."""

    private = tmp_path / "private"
    real = utc.shutil.rmtree

    @contextmanager
    def fake_sandbox(work_dir, **kwargs):
        for stale in tmp_path.glob("private.stale-*"):
            real(stale)
        private.mkdir()
        (private / "leftover").write_text("x")
        try:
            yield [], {}
        finally:
            with monkeypatch.context() as patch:
                patch.setattr(utc.shutil, "rmtree", _refuse)
                mos._remove_private_dir(str(private))

    def _refuse(path, *a, **k):
        raise OSError(1, "Operation not permitted", str(path))

    monkeypatch.setattr(mos, "model_sandbox", fake_sandbox)
    yield tmp_path
    monkeypatch.undo()
    for left in tmp_path.glob("private.stale-*"):
        real(left)


def test_cleanup_failure_after_a_finished_command_carries_the_result_3267(
    stuck_private_area, monkeypatch
):
    done = subprocess.CompletedProcess(["x"], 0, stdout="out", stderr="")
    monkeypatch.setattr(mos, "run_reaping_process_group", lambda *a, **k: done)
    with pytest.raises(mos.PrivateAreaNotRemoved) as info:
        mos.run_model_argv([sys.executable], work_dir=stuck_private_area, timeout=5)
    assert isinstance(info.value, mos.SandboxError)  # existing handlers still catch it
    assert info.value.result is done
    assert info.value.interrupted_by is None


def test_cleanup_failure_after_a_timeout_keeps_the_timeout_3267(stuck_private_area, monkeypatch):
    timeout = subprocess.TimeoutExpired(["x"], 5, output="partial")

    def times_out(*a, **k):
        raise timeout

    monkeypatch.setattr(mos, "run_reaping_process_group", times_out)
    with pytest.raises(mos.PrivateAreaNotRemoved) as info:
        mos.run_model_argv([sys.executable], work_dir=stuck_private_area, timeout=5)
    assert info.value.result is None
    assert info.value.interrupted_by is timeout


def test_command_string_cleanup_failure_carries_result_and_timeout_3267(
    stuck_private_area, monkeypatch
):
    done = subprocess.CompletedProcess(["x"], 0, stdout="out", stderr="")
    monkeypatch.setattr(mos, "run_command_string", lambda *a, **k: done)
    with pytest.raises(mos.PrivateAreaNotRemoved) as info:
        mos.run_model_command_string("true", work_dir=stuck_private_area, timeout=5)
    assert info.value.result is done

    timeout = subprocess.TimeoutExpired(["x"], 5)

    def times_out(*a, **k):
        raise timeout

    monkeypatch.setattr(mos, "run_command_string", times_out)
    with pytest.raises(mos.PrivateAreaNotRemoved) as info:
        mos.run_model_command_string("true", work_dir=stuck_private_area, timeout=5)
    assert info.value.interrupted_by is timeout


def test_scratch_tmp_cleanup_removes_a_deep_locked_tree_3281(tmp_path, monkeypatch):
    # real_outcome_scorer.clean_scratch_tmp: a test left a deep tree with a locked leaf.
    from nexus.research import real_outcome_scorer as scorer

    monkeypatch.setattr(utc, "_WALK_MAX_OPEN", 4)
    tmp = tmp_path / "tmp"
    tmp.mkdir()
    _deep_locked_tree(tmp / "left", 150)
    assert scorer.clean_scratch_tmp(tmp) == []
    assert list(tmp.iterdir()) == []


def test_scratch_tmp_cleanup_reports_a_tree_it_cannot_remove_3281(tmp_path, monkeypatch):
    from nexus.research import real_outcome_scorer as scorer

    tmp = tmp_path / "tmp"
    (tmp / "left").mkdir(parents=True)
    real = utc.shutil.rmtree
    monkeypatch.setattr(
        utc.shutil, "rmtree", lambda *a, **k: (_ for _ in ()).throw(OSError(1, "no"))
    )
    try:
        errors = scorer.clean_scratch_tmp(tmp)
        assert len(errors) == 1 and errors[0].startswith("rmtree:left:tree_not_removed:")
    finally:
        monkeypatch.undo()
        for left in tmp.glob("left.stale-*"):
            real(left)


def test_verifier_sandbox_from_the_previous_round_with_a_locked_leaf_is_replaced_3281(
    tmp_path, monkeypatch
):
    from nexus.committee.execution_verifier import PatchExecutionVerifier

    monkeypatch.setattr(utc, "_WALK_MAX_OPEN", 4)
    workspace = tmp_path / "ws"
    (workspace / ".nexus").mkdir(parents=True)
    (workspace / "a.py").write_text("x = 1\n")
    sandbox = workspace / ".nexus" / "run"
    _deep_locked_tree(sandbox, 120)
    verifier = object.__new__(PatchExecutionVerifier)
    verifier.workspace_root = workspace
    verifier._prepare_sandbox(sandbox, sandbox / "mirror")
    assert (sandbox / "home").is_dir() and (sandbox / "mirror" / "a.py").is_file()
    assert list((workspace / ".nexus").glob("run.stale-*")) == []


def test_confined_dir_copy_reports_a_staging_dir_it_cannot_remove_3281(tmp_path, monkeypatch):
    import nexus.engine.confined_test_runner as ctr

    (tmp_path / "test_a.py").write_text("def test_a():\n    pass\n")
    monkeypatch.setattr(ctr, "run_confined_test", lambda *a, **k: {"executed": True})
    real_remove = ctr.remove_untrusted_tree_quietly

    def remove_then_report(path):
        real_remove(path)
        return "tree_not_removed:x"

    monkeypatch.setattr(ctr, "remove_untrusted_tree_quietly", remove_then_report)
    result = ctr.run_pytest_dir_copy(tmp_path, "test_a.py")
    assert result == {"executed": True, "cleanup_error": "tree_not_removed:x"}
