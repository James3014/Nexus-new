"""nexus.core.hardened_git: linked worktree check and diff refusal.

Every repo here is a fresh ``git init`` under ``tmp_path``; each test moves the cwd to a
sentinel directory first.
"""

from __future__ import annotations

import os
import subprocess
import threading
from pathlib import Path

import pytest

from nexus.core import hardened_git


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    sentinel = tmp_path / "sentinel"
    sentinel.mkdir()
    monkeypatch.chdir(sentinel)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    return tmp_path


def _controller_and_worktree(env: Path) -> tuple[Path, Path]:
    repo = env / "controller"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.name", "t")
    _git(repo, "config", "user.email", "t@example.invalid")
    (repo / "a.txt").write_text("a\n", encoding="utf-8")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-qm", "base")
    worktree = env / "wt"
    _git(repo, "worktree", "add", "-q", "--detach", str(worktree))
    return repo, worktree


def test_a_linked_worktree_resolves_to_its_registration_in_the_controller(env):
    repo, worktree = _controller_and_worktree(env)

    git_dir = hardened_git.linked_worktree_git_dir(worktree, repo)

    assert git_dir == (repo / ".git" / "worktrees" / "wt").resolve()
    assert hardened_git.linked_worktree_git_dir(worktree) == git_dir
    head = hardened_git.run_hardened_git(worktree, "rev-parse", "HEAD", git_dir=git_dir)
    assert head.stdout.strip() == _git(repo, "rev-parse", "HEAD")


def test_a_git_pointer_into_the_worktree_itself_is_not_a_registration(env):
    repo, worktree = _controller_and_worktree(env)
    planted = worktree / "planted" / "worktrees" / "wt"
    planted.mkdir(parents=True)
    (planted / "commondir").write_text("../..\n", encoding="utf-8")
    (planted / "gitdir").write_text(f"{worktree / '.git'}\n", encoding="utf-8")
    (worktree / ".git").write_text(f"gitdir: {planted}\n", encoding="utf-8")

    assert hardened_git.linked_worktree_git_dir(worktree) is None
    assert hardened_git.linked_worktree_git_dir(worktree, repo) is None


def test_a_registration_in_another_controller_or_not_pointing_back_is_refused(env):
    repo, worktree = _controller_and_worktree(env)
    other = env / "other"
    other.mkdir()
    _git(other, "init", "-q")
    assert hardened_git.linked_worktree_git_dir(worktree, other) is None

    registration = repo / ".git" / "worktrees" / "wt"
    (registration / "gitdir").write_text(f"{env / 'elsewhere' / '.git'}\n", encoding="utf-8")
    assert hardened_git.linked_worktree_git_dir(worktree, repo) is None


def test_a_symlinked_pointer_or_a_plain_repository_is_not_a_linked_worktree(env):
    repo, worktree = _controller_and_worktree(env)
    assert hardened_git.linked_worktree_git_dir(repo) is None

    pointer = env / "pointer"
    pointer.write_text((worktree / ".git").read_text(encoding="utf-8"), encoding="utf-8")
    (worktree / ".git").unlink()
    (worktree / ".git").symlink_to(pointer)
    assert hardened_git.linked_worktree_git_dir(worktree, repo) is None


def test_the_runner_honours_a_caller_timeout(env, monkeypatch):
    _repo, worktree = _controller_and_worktree(env)
    seen: dict[str, object] = {}
    real_run = subprocess.run

    def recording_run(*args, **kwargs):
        seen["timeout"] = kwargs.get("timeout")
        return real_run(*args, **kwargs)

    monkeypatch.setattr(hardened_git.subprocess, "run", recording_run)
    hardened_git.run_hardened_git(worktree, "rev-parse", "HEAD", timeout=7.5)
    assert seen["timeout"] == 7.5
    hardened_git.run_hardened_git(worktree, "rev-parse", "HEAD")
    assert seen["timeout"] == hardened_git.GIT_TIMEOUT_S


@pytest.mark.parametrize(
    ("name", "refused"),
    [
        ("diff.renames", False),
        ("diff.algorithm", False),
        ("diff.mark.cachetextconv", False),
        ("diff.external", True),
        ("diff.mark.textconv", True),
        ("diff.mark.command", True),
    ],
)
def test_only_diff_keys_that_name_a_program_are_refused(name, refused):
    assert hardened_git.config_names_a_repository_program([name]) is refused


def _replace_with_prefilled_fifo(path: Path) -> int:
    """Swap ``path`` for a named pipe holding its old text; the returned fd keeps it open."""
    text = path.read_bytes()
    path.unlink()
    os.mkfifo(path)
    fd = os.open(path, os.O_RDWR)
    os.write(fd, text)
    return fd


def _returns_within(seconds: float, call):
    box: list = []

    def run() -> None:
        try:
            box.append((True, call()))
        except BaseException as exc:  # handed back to the caller below
            box.append((False, exc))

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join(seconds)
    assert not thread.is_alive(), "pointer read blocked on a non-regular file"
    ok, value = box[0]
    if not ok:
        raise value
    return value


def test_a_commondir_replaced_by_a_named_pipe_fails_closed_promptly(env):
    _, worktree = _controller_and_worktree(env)
    registration = hardened_git.linked_worktree_git_dir(worktree)
    fd = _replace_with_prefilled_fifo(registration / "commondir")
    try:
        assert _returns_within(5, lambda: hardened_git.linked_worktree_git_dir(worktree)) is None
        result = _returns_within(
            5, lambda: hardened_git.run_hardened_git(worktree, "status", git_dir=registration)
        )
        assert result.returncode != 0
    finally:
        os.close(fd)


def test_a_gitdir_pointer_replaced_by_a_named_pipe_fails_closed_promptly(env):
    _, worktree = _controller_and_worktree(env)
    registration = hardened_git.linked_worktree_git_dir(worktree)
    fd = _replace_with_prefilled_fifo(registration / "gitdir")
    try:
        assert _returns_within(5, lambda: hardened_git.linked_worktree_git_dir(worktree)) is None
    finally:
        os.close(fd)


def test_a_dot_git_pointer_replaced_by_a_named_pipe_fails_closed_promptly(env):
    _, worktree = _controller_and_worktree(env)
    fd = _replace_with_prefilled_fifo(worktree / ".git")
    try:
        assert _returns_within(5, lambda: hardened_git.linked_worktree_git_dir(worktree)) is None
        with pytest.raises(OSError):
            _returns_within(5, lambda: hardened_git._read_pointer_file(worktree / ".git"))
    finally:
        os.close(fd)


def test_an_oversized_pointer_file_is_refused_not_read(env):
    _, worktree = _controller_and_worktree(env)
    registration = hardened_git.linked_worktree_git_dir(worktree)
    pointer = registration / "commondir"
    pointer.write_text(pointer.read_text(encoding="utf-8") + " " * 5000, encoding="utf-8")
    with pytest.raises(OSError):
        hardened_git._read_pointer_file(pointer)
    assert hardened_git.linked_worktree_git_dir(worktree) is None


@pytest.mark.parametrize("pointer", ["commondir", "gitdir"])
def test_a_registration_pointer_that_is_a_named_pipe_with_no_writer_fails_closed_promptly(
    env, pointer
):
    """No writer holds the pipe open, so a blocking open would never return."""
    _, worktree = _controller_and_worktree(env)
    registration = hardened_git.linked_worktree_git_dir(worktree)
    (registration / pointer).unlink()
    os.mkfifo(registration / pointer)

    assert _returns_within(5, lambda: hardened_git.linked_worktree_git_dir(worktree)) is None
    result = _returns_within(
        5, lambda: hardened_git.run_hardened_git(worktree, "status", git_dir=registration)
    )
    assert result.returncode == 128


@pytest.mark.parametrize("pointer", ["commondir", "gitdir"])
def test_a_registration_pointer_that_is_a_symlink_is_refused(env, pointer):
    _, worktree = _controller_and_worktree(env)
    registration = hardened_git.linked_worktree_git_dir(worktree)
    link = registration / pointer
    link.rename(registration / f"{pointer}.real")
    os.symlink(f"{pointer}.real", link)

    assert hardened_git.linked_worktree_git_dir(worktree) is None
    assert hardened_git.run_hardened_git(worktree, "status", git_dir=registration).returncode == 128


def test_a_pointer_file_of_exactly_the_size_limit_is_still_read(env):
    _, worktree = _controller_and_worktree(env)
    registration = hardened_git.linked_worktree_git_dir(worktree)
    dotgit = worktree / ".git"
    text = dotgit.read_text(encoding="utf-8")
    dotgit.write_text(text + "\n" * (4096 - len(text.encode("utf-8"))), encoding="utf-8")
    assert len(dotgit.read_bytes()) == 4096

    assert hardened_git.linked_worktree_git_dir(worktree) == registration


def test_a_short_read_of_a_pointer_file_is_refused(env, monkeypatch):
    _, worktree = _controller_and_worktree(env)
    registration = hardened_git.linked_worktree_git_dir(worktree)
    real_read = os.read
    monkeypatch.setattr(hardened_git.os, "read", lambda fd, n: real_read(fd, n)[:5])

    with pytest.raises(OSError):
        hardened_git._read_pointer_file(registration / "commondir")
    assert hardened_git.linked_worktree_git_dir(worktree) is None


def test_a_pointer_file_larger_than_the_limit_is_refused_by_its_size(env, monkeypatch):
    _, worktree = _controller_and_worktree(env)
    registration = hardened_git.linked_worktree_git_dir(worktree)
    pointer = registration / "commondir"
    pointer.write_text(pointer.read_text(encoding="utf-8") + " " * 5000, encoding="utf-8")
    real_read = os.read
    monkeypatch.setattr(hardened_git.os, "read", lambda fd, n: real_read(fd, 64))

    with pytest.raises(OSError):
        hardened_git._read_pointer_file(pointer)
