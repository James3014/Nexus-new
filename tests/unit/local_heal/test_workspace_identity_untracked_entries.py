"""``ReproductionRunner.workspace_identity`` reads untracked entries the repro script may have
written: links are bound by their text and never followed, only regular files are read, without
blocking, and within a total byte budget; anything else leaves the source unbound.
"""

from __future__ import annotations

import os
import stat
import subprocess
import threading
from pathlib import Path

import pytest

from nexus.services.local_heal import reproduction
from nexus.services.local_heal.reproduction import ReproductionRunner


def _git_repo(path: Path) -> Path:
    path.mkdir()
    for args in (
        ["init", "-q"],
        ["config", "user.email", "test@example.com"],
        ["config", "user.name", "Test"],
    ):
        subprocess.run(["git", *args], cwd=path, check=True)
    (path / "src.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "src.py"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "fixture"], cwd=path, check=True)
    return path


def _identity(repo: Path, timeout: float = 5.0) -> tuple[str, bool]:
    out: list[tuple[str, bool]] = []
    thread = threading.Thread(
        target=lambda: out.append(ReproductionRunner(repo).workspace_identity()), daemon=True
    )
    thread.start()
    thread.join(timeout=timeout)
    assert not thread.is_alive(), "workspace_identity blocked"
    return out[0]


def test_untracked_regular_file_content_is_bound(tmp_path):
    repo = _git_repo(tmp_path / "repo")
    (repo / "new.py").write_text("a", encoding="utf-8")
    first = _identity(repo)
    (repo / "new.py").write_text("b", encoding="utf-8")
    second = _identity(repo)
    assert first[1] is True and second[1] is True
    assert first[0] != second[0]


def test_untracked_link_is_bound_by_its_text_not_followed(tmp_path):
    repo = _git_repo(tmp_path / "repo")
    outside = tmp_path / "outside.txt"
    outside.write_text("one", encoding="utf-8")
    (repo / "link").symlink_to(outside)
    first = _identity(repo)
    outside.write_text("two", encoding="utf-8")
    second = _identity(repo)
    assert first == second and first[1] is True

    (repo / "link").unlink()
    (repo / "link").symlink_to(tmp_path / "elsewhere.txt")
    assert _identity(repo)[0] != first[0]


def test_untracked_link_to_a_fifo_does_not_block(tmp_path):
    repo = _git_repo(tmp_path / "repo")
    os.mkfifo(repo / "p")
    (repo / "l").symlink_to("p")
    identity, bound = _identity(repo)
    assert bound is True and identity.startswith("HEAD=")


def test_untracked_link_to_an_endless_device_does_not_read_it(tmp_path):
    repo = _git_repo(tmp_path / "repo")
    (repo / "z").symlink_to("/dev/zero")
    assert _identity(repo)[1] is True


def test_untracked_files_over_the_byte_budget_leave_the_source_unbound(tmp_path, monkeypatch):
    repo = _git_repo(tmp_path / "repo")
    monkeypatch.setattr(reproduction, "_WORKSPACE_UNTRACKED_MAX_BYTES", 10)
    (repo / "a.bin").write_bytes(b"x" * 6)
    (repo / "b.bin").write_bytes(b"y" * 4)
    assert _identity(repo)[1] is True  # exactly at the budget, summed over files
    (repo / "c.bin").write_bytes(b"z")
    assert _identity(repo) == ("", False)


def test_large_sparse_file_is_not_read_past_the_budget(tmp_path, monkeypatch):
    repo = _git_repo(tmp_path / "repo")
    monkeypatch.setattr(reproduction, "_WORKSPACE_UNTRACKED_MAX_BYTES", 1024 * 1024)
    with open(repo / "sparse.bin", "wb") as handle:
        handle.truncate(64 * 1024 * 1024)
    assert _identity(repo) == ("", False)


def test_non_regular_entry_is_unbound_and_never_opened(tmp_path, monkeypatch):
    # Opening a device node can itself have effects: only a regular file is ever opened.
    fifo = tmp_path / "p"
    os.mkfifo(fifo)

    def no_open(*args, **kwargs):
        raise AssertionError("non-regular entry was opened")

    monkeypatch.setattr(reproduction.os, "open", no_open)
    assert ReproductionRunner._untracked_digest(fifo, [1 << 20]) is None


def test_fifo_swapped_in_after_lstat_is_not_read(tmp_path, monkeypatch):
    fifo = tmp_path / "p"
    os.mkfifo(fifo)
    regular = os.lstat(__file__)
    real_lstat = os.lstat
    monkeypatch.setattr(
        reproduction.os,
        "lstat",
        lambda path: regular if Path(path) == fifo else real_lstat(path),
    )
    assert stat.S_ISREG(reproduction.os.lstat(fifo).st_mode)
    out: list = []
    thread = threading.Thread(
        target=lambda: out.append(ReproductionRunner._untracked_digest(fifo, [1 << 20])),
        daemon=True,
    )
    thread.start()
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert out == [None]


def test_link_swapped_in_after_lstat_is_not_followed(tmp_path, monkeypatch):
    target = tmp_path / "secret.txt"
    target.write_text("s", encoding="utf-8")
    link = tmp_path / "l"
    link.symlink_to(target)
    regular = os.lstat(target)
    real_lstat = os.lstat
    monkeypatch.setattr(
        reproduction.os,
        "lstat",
        lambda path: regular if Path(path) == link else real_lstat(path),
    )
    with pytest.raises(OSError):
        ReproductionRunner._untracked_digest(link, [1 << 20])
