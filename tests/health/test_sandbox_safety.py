from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from nexus.health import sandbox as sandbox_module
from nexus.health.executor import RepairExecutor
from nexus.health.sandbox import SpeculativeSandbox


def test_tmpdir_fork_preserves_external_symlink_without_copying_target(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "repo.txt").write_text("repo", encoding="utf-8")
    external = tmp_path / "external"
    external.mkdir()
    (external / "large.bin").write_bytes(b"x" * (2 * 1024 * 1024))
    (source / "escape").symlink_to(external, target_is_directory=True)

    sandbox = SpeculativeSandbox(source, mode="tmpdir")
    sandbox_root = sandbox.fork()
    try:
        copied_link = sandbox_root / "escape"
        assert copied_link.is_symlink()
        assert Path(os.readlink(copied_link)) == external

        visited_files = []
        for _root, _dirs, files in os.walk(sandbox_root, followlinks=False):
            visited_files.extend(files)
        assert "large.bin" not in visited_files
    finally:
        sandbox.cleanup()


def test_fork_failure_removes_partial_sandbox(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    partial_root = tmp_path / "nexus_sandbox_partial"

    def fake_mkdtemp(*, prefix: str) -> str:
        assert prefix == "nexus_sandbox_"
        partial_root.mkdir()
        return str(partial_root)

    def exploding_copytree(_src, dst, **_kwargs):
        dst = Path(dst)
        dst.mkdir(parents=True)
        (dst / "partial.txt").write_text("partial", encoding="utf-8")
        raise OSError("injected copy failure")

    monkeypatch.setattr(sandbox_module.tempfile, "mkdtemp", fake_mkdtemp)
    monkeypatch.setattr(sandbox_module.shutil, "copytree", exploding_copytree)

    sandbox = SpeculativeSandbox(source, mode="tmpdir")
    with pytest.raises(OSError, match="injected copy failure"):
        sandbox.fork()

    assert not partial_root.exists()
    assert sandbox.sandbox_root is None
    assert sandbox._temp_root is None


def test_cleanup_does_not_follow_symlink_outside_sandbox(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    sentinel = external / "sentinel.txt"
    sentinel.write_text("keep", encoding="utf-8")
    (source / "escape").symlink_to(external, target_is_directory=True)

    sandbox = SpeculativeSandbox(source, mode="tmpdir")
    sandbox_root = sandbox.fork()
    assert (sandbox_root / "escape").is_symlink()

    sandbox.cleanup()

    assert sentinel.read_text(encoding="utf-8") == "keep"
    assert external.exists()


def test_cleanup_is_idempotent(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "file.txt").write_text("content", encoding="utf-8")

    sandbox = SpeculativeSandbox(source, mode="tmpdir")
    sandbox_root = sandbox.fork()
    temp_root = sandbox_root.parent

    sandbox.cleanup()
    sandbox.cleanup()

    assert not temp_root.exists()
    assert sandbox.sandbox_root is None
    assert sandbox._temp_root is None


def test_broad_source_roots_are_rejected_before_temp_creation(monkeypatch, tmp_path: Path) -> None:
    created = False

    def unexpected_mkdtemp(*, prefix: str) -> str:
        nonlocal created
        created = True
        return str(tmp_path / prefix)

    monkeypatch.setattr(sandbox_module.tempfile, "mkdtemp", unexpected_mkdtemp)

    sandbox = SpeculativeSandbox(Path(tempfile.gettempdir()), mode="tmpdir")
    with pytest.raises(ValueError, match="too broad"):
        sandbox.fork()

    assert created is False
    assert sandbox.sandbox_root is None


def test_source_root_symlink_is_rejected(tmp_path: Path) -> None:
    real_source = tmp_path / "real-source"
    real_source.mkdir()
    linked_source = tmp_path / "linked-source"
    linked_source.symlink_to(real_source, target_is_directory=True)

    sandbox = SpeculativeSandbox(linked_source, mode="tmpdir")
    with pytest.raises(ValueError, match="must not be a symlink"):
        sandbox.fork()


def test_normal_tmpdir_fork_copies_regular_files(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "file.txt").write_text("content", encoding="utf-8")

    sandbox = SpeculativeSandbox(source, mode="tmpdir")
    sandbox_root = sandbox.fork()
    try:
        assert (sandbox_root / "file.txt").read_text(encoding="utf-8") == "content"
    finally:
        sandbox.cleanup()


def test_executor_cleanup_runs_when_fork_raises_after_partial_initialization(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    partial_root = tmp_path / "nexus_sandbox_executor_partial"

    monkeypatch.setattr(SpeculativeSandbox, "_docker_available", staticmethod(lambda: False))

    def partial_fork(self: SpeculativeSandbox) -> Path:
        partial_root.mkdir()
        self._temp_root = partial_root
        self.sandbox_root = partial_root / "repo"
        self.sandbox_root.mkdir()
        (self.sandbox_root / "partial.txt").write_text("partial", encoding="utf-8")
        raise OSError("injected fork failure")

    monkeypatch.setattr(SpeculativeSandbox, "fork", partial_fork)

    executor = RepairExecutor(repo_root, task_runner=lambda _manifest: 0)
    rc, note = executor._validate_in_sandbox([])

    assert rc == 1
    assert note.startswith("sandbox_error:OSError:injected fork failure")
    assert not partial_root.exists()
